import errno
import hmac
import ipaddress
import json
import os
import re
import sqlite3
import sys
from urllib.parse import urlencode
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

app = Flask(__name__)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB = os.path.join(BASE_DIR, "data", "sff.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
DB = os.path.abspath(os.environ.get("DATABASE_PATH", DEFAULT_DB))
USING_POSTGRES = bool(DATABASE_URL)
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "").strip().rstrip("/")
APP_ENV = os.environ.get("APP_ENV", "").strip().lower()
DATABASE_ERRORS = (sqlite3.Error,)
if psycopg is not None:
    DATABASE_ERRORS += (psycopg.Error,)


def is_local_hostname(hostname):
    hostname = (hostname or "").lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


if PUBLIC_SITE_URL:
    parsed_site_url = urlsplit(PUBLIC_SITE_URL)
    if (
        parsed_site_url.scheme not in {"http", "https"}
        or not parsed_site_url.netloc
        or not parsed_site_url.hostname
        or parsed_site_url.username
        or parsed_site_url.password
        or parsed_site_url.path not in {"", "/"}
        or parsed_site_url.query
        or parsed_site_url.fragment
    ):
        raise RuntimeError(
            "PUBLIC_SITE_URL must be an absolute site origin without a path, query, or fragment."
        )
    if APP_ENV == "production" and parsed_site_url.scheme != "https":
        raise RuntimeError("PUBLIC_SITE_URL must use HTTPS in production.")
    if APP_ENV == "production" and is_local_hostname(parsed_site_url.hostname):
        raise RuntimeError("PUBLIC_SITE_URL must be a public domain, not localhost.")

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY"),
    OWNER_WHATSAPP_NUMBER=os.environ.get("OWNER_WHATSAPP_NUMBER", "").strip(),
    PUBLIC_SITE_URL=PUBLIC_SITE_URL,
    MAX_CONTENT_LENGTH=32 * 1024
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if APP_ENV == "production":
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY must be set when APP_ENV=production.")
    app.config["SESSION_COOKIE_SECURE"] = True
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

IMAGE_MAP = {
    "rohu": "/static/fish-rohu.svg",
    "katla": "/static/fish-katla.svg",
    "pomfret": "/static/fish-pomfret.svg",
    "prawns": "/static/fish-prawns.svg",
    "somasila fish": "/static/fish-rohu.svg",
    "nellore fish": "/static/fish-katla.svg",
    "fresh prawns": "/static/fish-prawns.svg",
    "fresh pomfret": "/static/fish-pomfret.svg",
}
SITE_DESCRIPTION = (
    "Somasila Fresh Fish supplies fresh and dry fish in bulk to customers "
    "within Nellore and Kadapa districts."
)


class DatabaseConnection:
    def __init__(self, connection, is_postgres):
        self.connection = connection
        self.is_postgres = is_postgres

    def execute(self, statement, parameters=()):
        if self.is_postgres:
            statement = statement.replace("?", "%s")
        return self.connection.execute(statement, parameters)

    def executemany(self, statement, parameters):
        if self.is_postgres:
            statement = statement.replace("?", "%s")
        return self.connection.executemany(statement, parameters)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def connect_db():
    if USING_POSTGRES:
        if psycopg is None:
            raise RuntimeError(
                "PostgreSQL is configured but psycopg is missing. "
                "Install the packages in python/requirements.txt."
            )
        connection = psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            connect_timeout=10,
            sslmode="require"
        )
        return DatabaseConnection(connection, is_postgres=True)

    connection = sqlite3.connect(DB, timeout=10)
    connection.row_factory = sqlite3.Row
    return DatabaseConnection(connection, is_postgres=False)


def valid_owner_whatsapp_number():
    number = app.config.get("OWNER_WHATSAPP_NUMBER")
    if isinstance(number, str) and re.fullmatch(r"[1-9][0-9]{7,14}", number):
        return number
    return None


def public_site_origin():
    if app.config["PUBLIC_SITE_URL"]:
        return app.config["PUBLIC_SITE_URL"]

    host = request.host
    hostname = (urlsplit(f"//{host}").hostname or "").lower()
    if APP_ENV == "production":
        if is_local_hostname(hostname):
            return None
        return f"https://{host}"
    if is_local_hostname(hostname):
        return None
    return request.url_root.rstrip("/")


def page_seo_metadata():
    origin = public_site_origin()
    canonical_url = f"{origin}{request.path}" if origin else None
    organization = {
        "@type": "Organization",
        "name": "Somasila Fresh Fish",
        "description": SITE_DESCRIPTION,
        "areaServed": ["Nellore district", "Kadapa district"]
    }
    website = {
        "@type": "WebSite",
        "name": "Somasila Fresh Fish",
        "description": SITE_DESCRIPTION
    }
    if origin:
        organization_id = f"{origin}/#organization"
        organization.update({
            "@id": organization_id,
            "url": origin
        })
        website.update({
            "@id": f"{origin}/#website",
            "url": origin,
            "publisher": {"@id": organization_id}
        })

    return {
        "title": (
            "Fresh and Dry Fish Products | Somasila Fresh Fish"
            if request.path == "/products"
            else "Somasila Fresh Fish | Fresh Fish and Dry Fish Supply"
        ),
        "description": SITE_DESCRIPTION,
        "keywords": (
            "Somasila Fresh Fish, fresh fish bulk orders, dry fish, "
            "Nellore, Kadapa"
        ),
        "google_site_verification": os.environ.get(
            "GOOGLE_SITE_VERIFICATION", ""
        ).strip(),
        "canonical_url": canonical_url,
        "og_image": (
            f"{origin}{url_for('static', filename='fish-rohu.svg')}"
            if origin else None
        ),
        "structured_data": {
            "@context": "https://schema.org",
            "@graph": [organization, website]
        }
    }


def load_public_products():
    con = connect_db()
    try:
        products = con.execute(
            "SELECT * FROM products ORDER BY id"
        ).fetchall()
        result = []
        for product in products:
            item = dict(product)
            item["image"] = IMAGE_MAP.get(
                str(item.get("image", "")).lower(),
                item.get("image")
            )
            result.append(item)
        return result
    finally:
        con.close()


def owner_auth_required():
    password = os.environ.get("OWNER_PASSWORD")
    if not password:
        abort(503, description="Owner dashboard is disabled. Set OWNER_PASSWORD first.")

    credentials = request.authorization
    if (
        credentials is None
        or credentials.username != "owner"
        or not hmac.compare_digest(credentials.password or "", password)
    ):
        return Response(
            "Owner login required",
            401,
            {"WWW-Authenticate": 'Basic realm="SFF Owner Orders"'}
        )

    return None


def setup_db():
    con = None
    try:
        if not USING_POSTGRES:
            db_directory = os.path.dirname(DB)
            if db_directory:
                os.makedirs(db_directory, exist_ok=True)
        con = connect_db()
        if USING_POSTGRES:
            con.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    image TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    customer TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    address TEXT NOT NULL,
                    items TEXT NOT NULL,
                    total DOUBLE PRECISION NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Pending'
                )
            """)
            con.execute(
                "ALTER TABLE orders ADD COLUMN IF NOT EXISTS "
                "status TEXT NOT NULL DEFAULT 'Pending'"
            )
        else:
            con.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    image TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    address TEXT NOT NULL,
                    items TEXT NOT NULL,
                    total REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Pending'
                )
            """)
            order_columns = {
                column["name"]
                for column in con.execute("PRAGMA table_info(orders)").fetchall()
            }
            if "status" not in order_columns:
                con.execute(
                    "ALTER TABLE orders ADD COLUMN status TEXT NOT NULL DEFAULT 'Pending'"
                )

        products = [
            ("Somasila Royallu", 240, IMAGE_MAP["rohu"]),
            ("Somasila Gendi", 260, IMAGE_MAP["katla"]),
            ("Kaki Gendi", 420, IMAGE_MAP["pomfret"]),
            ("Somasila Bochi", 320, IMAGE_MAP["prawns"])
        ]
        if con.execute("SELECT 1 FROM products LIMIT 1").fetchone() is None:
            con.executemany(
                "INSERT INTO products (name, price, image) VALUES (?, ?, ?)",
                products
            )

        con.commit()
    except (OSError,) + DATABASE_ERRORS as error:
        database_target = "PostgreSQL" if USING_POSTGRES else DB
        app.logger.exception("Could not initialize database (%s)", database_target)
        raise RuntimeError(
            "Database initialization failed. Check DATABASE_URL for PostgreSQL, "
            "or DATABASE_PATH and folder permissions for SQLite."
        ) from error
    finally:
        if con is not None:
            con.close()


@app.route("/")
def home():
    return render_template(
        "index.html",
        owner_whatsapp_number=valid_owner_whatsapp_number(),
        products=load_public_products(),
        seo=page_seo_metadata()
    )


@app.route("/products")
def products_page():
    return render_template(
        "index.html",
        owner_whatsapp_number=valid_owner_whatsapp_number(),
        products=load_public_products(),
        seo=page_seo_metadata()
    )


@app.route("/robots.txt")
def robots_txt():
    origin = public_site_origin()
    directives = ["User-agent: *", "Allow: /"]
    if origin:
        directives.append(f"Sitemap: {origin}/sitemap.xml")
    content = "\n".join(directives + [""])
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    origin = public_site_origin()
    if not origin:
        return Response(
            "A public HTTPS domain is required before a sitemap can be generated.",
            status=503,
            mimetype="text/plain"
        )
    public_paths = [url_for("home"), url_for("products_page")]
    locations = "".join(
        f"<url><loc>{escape(origin + path)}</loc></url>"
        for path in public_paths
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{locations}</urlset>"
    )
    return Response(xml, mimetype="application/xml")


@app.route("/healthz")
def health_check():
    con = connect_db()
    try:
        con.execute("SELECT 1")
    finally:
        con.close()
    return jsonify({"status": "ok"})


@app.before_request
def normalize_malformed_products_url():
    if request.path == "/products\u2061A0":
        return redirect(url_for("products_page"), code=302)
    return None


@app.after_request
def prevent_indexing_private_routes(response):
    if (
        request.path == "/owner"
        or request.path.startswith("/api/orders")
        or request.path.startswith("/api/owner/")
        or request.path == "/healthz"
    ):
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    return response


@app.route("/api/products")
def get_products():
    return jsonify(load_public_products())


@app.route("/api/orders", methods=["POST"])
def place_order():
    data = request.get_json(silent=True) or {}

    owner_whatsapp_number = valid_owner_whatsapp_number()
    if owner_whatsapp_number is None:
        return jsonify({
            "error": "Owner WhatsApp number is missing or invalid. Please contact the shop directly."
        }), 503

    if not isinstance(data, dict):
        return jsonify({"error": "Invalid order details"}), 400

    customer = data.get("customer")
    phone = data.get("phone")
    address = data.get("address")
    items = data.get("items", [])

    if not all(isinstance(value, str) for value in (customer, phone, address)):
        return jsonify({"error": "Customer, phone, and address must be text"}), 400

    customer = customer.strip()
    phone = phone.strip()
    address = address.strip()
    if not customer or not phone or not address:
        return jsonify({"error": "Fill all customer details"}), 400

    if len(customer) > 120 or len(address) > 500:
        return jsonify({"error": "Name must be at most 120 characters and address at most 500"}), 400

    if re.fullmatch(r"[0-9]{10}", phone) is None:
        return jsonify({"error": "Enter a valid 10-digit phone number"}), 400

    if not isinstance(items, list) or not items or len(items) > 50:
        return jsonify({"error": "Invalid order items"}), 400

    con = connect_db()
    total = 0
    verified_items = []

    try:
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Invalid order item")
            product_id = item.get("id")
            qty = item.get("qty")

            if (
                type(product_id) is not int
                or type(qty) is not int
                or qty < 1
                or qty > 100
            ):
                raise ValueError("Invalid quantity")

            product = con.execute(
                "SELECT id, name, price FROM products WHERE id = ?",
                (product_id,)
            ).fetchone()

            if product is None:
                raise ValueError("Product not found")

            subtotal = product["price"] * qty
            total += subtotal

            verified_items.append({
                "id": product["id"],
                "name": product["name"],
                "qty": qty,
                "price": product["price"],
                "subtotal": subtotal
            })

        cursor = con.execute("""
            INSERT INTO orders
            (customer, phone, address, items, total)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        """, (
            customer, phone, address,
            json.dumps(verified_items),
            total
        ))
        order_id = cursor.fetchone()["id"]
        con.commit()
        whatsapp_lines = [
            f"Order ID: {order_id}",
            f"Customer name: {customer}",
            f"Customer mobile: {phone}",
            f"Delivery address: {address}",
            "Fish products:"
        ]
        whatsapp_lines.extend(
            f"- {item['name']} x {item['qty']} @ ₹{item['price']:.2f} each = ₹{item['subtotal']:.2f}"
            for item in verified_items
        )
        whatsapp_lines.append(f"Total amount: ₹{total:.2f}")
        whatsapp_url = (
            f"https://wa.me/{owner_whatsapp_number}?"
            f"{urlencode({'text': chr(10).join(whatsapp_lines)})}"
        )
        return jsonify({
            "message": "Order placed successfully",
            "order_id": order_id,
            "total": round(total, 2),
            "whatsapp_url": whatsapp_url
        }), 201

    except (ValueError, TypeError, KeyError):
        return jsonify({"error": "Invalid product or quantity"}), 400

    finally:
        con.close()


def handle_database_error(error):
    app.logger.exception("Database request failed")
    if request.path.startswith("/api/"):
        return jsonify({
            "error": "The database is temporarily unavailable. Please try again."
        }), 503
    return "The database is temporarily unavailable. Please try again.", 503


for database_error in DATABASE_ERRORS:
    app.register_error_handler(database_error, handle_database_error)


@app.route("/api/orders")
def get_orders():
    phone = request.args.get("phone", "").strip()
    if not phone.isdigit() or len(phone) != 10:
        return jsonify({"error": "Enter a valid 10-digit phone number"}), 400

    con = connect_db()
    try:
        orders = con.execute(
            "SELECT id, items, total, status FROM orders WHERE phone = ? ORDER BY id DESC",
            (phone,)
        ).fetchall()
        result = [
            {
                "id": order["id"],
                "items": json.loads(order["items"]),
                "total": order["total"],
                "status": order["status"]
            }
            for order in orders
        ]
        return jsonify(result)
    finally:
        con.close()


@app.route("/owner")
def owner_orders_page():
    auth_response = owner_auth_required()
    if auth_response:
        return auth_response
    return render_template("owner.html")


@app.route("/api/owner/orders")
def get_owner_orders():
    auth_response = owner_auth_required()
    if auth_response:
        return auth_response

    con = connect_db()
    try:
        orders = con.execute(
            "SELECT id, customer, phone, address, items, total, status "
            "FROM orders ORDER BY id DESC"
        ).fetchall()
        return jsonify([
            {
                "id": order["id"],
                "customer": order["customer"],
                "phone": order["phone"],
                "address": order["address"],
                "items": json.loads(order["items"]),
                "total": order["total"],
                "status": order["status"]
            }
            for order in orders
        ])
    finally:
        con.close()


@app.route("/api/owner/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    auth_response = owner_auth_required()
    if auth_response:
        return auth_response

    data = request.get_json(silent=True) or {}
    status = data.get("status")
    allowed_statuses = {"Pending", "Out for delivery", "Delivered"}
    if not isinstance(status, str) or status not in allowed_statuses:
        return jsonify({"error": "Invalid delivery status"}), 400

    con = connect_db()
    try:
        cursor = con.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (status, order_id)
        )
        if cursor.rowcount == 0:
            return jsonify({"error": "Order not found"}), 404
        con.commit()
        return jsonify({"id": order_id, "status": status})
    finally:
        con.close()


setup_db()


if __name__ == "__main__":
    host = os.environ.get("SFF_HOST", "0.0.0.0")
    try:
        port = int(os.environ.get("PORT", "5000"))
    except ValueError as error:
        raise SystemExit("PORT must be a valid integer.") from error
    try:
        app.run(host=host, port=port, debug=False)
    except OSError as error:
        if error.errno in (errno.EADDRINUSE, 10048):
            print(
                f"Port {port} is already in use. Stop the other server or set PORT to a free port.",
                file=sys.stderr
            )
            raise SystemExit(1) from error
        raise