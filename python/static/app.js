const productList = document.getElementById('product-list');
const cartCount = document.getElementById('cart-count');
const cartItems = document.getElementById('cart-items');
const cartTotal = document.getElementById('cart-total');
const orderForm = document.getElementById('order-form');
const orderMessage = document.getElementById('order-message');
const ordersForm = document.getElementById('orders-form');
const ordersMessage = document.getElementById('orders-message');
const ordersList = document.getElementById('orders-list');

const state = {
  products: [],
  cart: []
};
let orderSubmissionInProgress = false;

function formatPrice(value) {
  return `₹${Number(value).toFixed(2)}`;
}

function getProductImage(product) {
  if (product.image && product.image.startsWith('http')) {
    return product.image;
  }

  const fallbackImages = {
    rohu: '/static/fish-rohu.svg',
    katla: '/static/fish-katla.svg',
    pomfret: '/static/fish-pomfret.svg',
    prawns: '/static/fish-prawns.svg'
  };

  const key = String(product.name || '').toLowerCase();
  return fallbackImages[key.includes('rohu') ? 'rohu' : key.includes('katla') ? 'katla' : key.includes('pomfret') ? 'pomfret' : key.includes('prawn') ? 'prawns' : 'rohu'];
}

function renderProducts() {
  if (!productList) return;

  productList.innerHTML = state.products.map((product) => `
    <article class="product-card">
      <img src="${getProductImage(product)}" alt="${product.name} illustration offered in bulk by Somasila Fresh Fish" class="product-image" />
      <div class="product-info">
        <h3>${product.name}</h3>
        <p class="product-price">${formatPrice(product.price)}</p>
        <button class="add-btn" data-id="${product.id}">Add to cart</button>
      </div>
    </article>
  `).join('');

  productList.querySelectorAll('.add-btn').forEach((button) => {
    button.addEventListener('click', () => addToCart(Number(button.dataset.id)));
  });
}

function addToCart(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;

  const existing = state.cart.find((item) => item.id === productId);
  if (existing) {
    existing.qty += 1;
  } else {
    state.cart.push({ ...product, qty: 1 });
  }

  renderCart();
}

function removeFromCart(productId) {
  state.cart = state.cart.filter((item) => item.id !== productId);
  renderCart();
}

function updateQty(productId, change) {
  const item = state.cart.find((cartItem) => cartItem.id === productId);
  if (!item) return;

  item.qty += change;
  if (item.qty <= 0) {
    removeFromCart(productId);
    return;
  }

  renderCart();
}

function renderCart() {
  if (!cartItems || !cartTotal || !cartCount) return;

  if (state.cart.length === 0) {
    cartItems.innerHTML = 'Your cart is empty.';
    cartTotal.textContent = '0';
    cartCount.textContent = '0';
    return;
  }

  const total = state.cart.reduce((sum, item) => sum + item.price * item.qty, 0);
  cartCount.textContent = String(state.cart.reduce((sum, item) => sum + item.qty, 0));
  cartTotal.textContent = String(Math.round(total));

  cartItems.innerHTML = state.cart.map((item) => `
    <div class="cart-item">
      <div>
        <strong>${item.name}</strong><br>
        <span>${formatPrice(item.price)} each</span>
      </div>
      <div class="qty-box">
        <button type="button" data-action="decrease" data-id="${item.id}">-</button>
        <span>${item.qty}</span>
        <button type="button" data-action="increase" data-id="${item.id}">+</button>
      </div>
    </div>
  `).join('');

  cartItems.querySelectorAll('button[data-action]').forEach((button) => {
    button.addEventListener('click', () => {
      const productId = Number(button.dataset.id);
      const action = button.dataset.action;
      updateQty(productId, action === 'increase' ? 1 : -1);
    });
  });
}

async function loadProducts() {
  try {
    const response = await fetch('/api/products');
    if (!response.ok) {
      throw new Error(`Failed to load products: ${response.status}`);
    }

    state.products = await response.json();
    renderProducts();
  } catch (error) {
    productList.innerHTML = '<p>Unable to load fish products right now.</p>';
    console.error(error);
  }
}

ordersForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  ordersMessage.textContent = 'Looking up your orders...';
  ordersList.replaceChildren();

  const phone = new FormData(ordersForm).get('phone');

  try {
    const response = await fetch(`/api/orders?phone=${encodeURIComponent(phone)}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Unable to look up orders');
    }

    if (data.length === 0) {
      ordersMessage.textContent = 'No orders found for that phone number.';
      return;
    }

    ordersMessage.textContent = `Found ${data.length} order${data.length === 1 ? '' : 's'}.`;
    for (const order of data) {
      const card = document.createElement('article');
      card.className = 'order-card';
      const title = document.createElement('h3');
      title.textContent = `Order #${order.id}`;
      const status = document.createElement('p');
      status.textContent = `Delivery status: ${order.status}`;
      const items = document.createElement('ul');
      for (const item of order.items) {
        const entry = document.createElement('li');
        entry.textContent = `${item.name} x ${item.qty} — ${formatPrice(item.subtotal)}`;
        items.append(entry);
      }
      const total = document.createElement('p');
      total.textContent = `Total: ${formatPrice(order.total)}`;
      card.append(title, status, items, total);
      ordersList.append(card);
    }
  } catch (error) {
    ordersMessage.textContent = error.message;
  }
});

orderForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  if (orderSubmissionInProgress) return;

  if (!state.cart.length) {
    orderMessage.textContent = 'Please add at least one fish to your cart.';
    orderMessage.style.color = '#c0392b';
    return;
  }

  const form = new FormData(orderForm);
  const payload = {
    customer: form.get('customer'),
    phone: form.get('phone'),
    address: form.get('address'),
    items: state.cart.map((item) => ({ id: item.id, qty: item.qty }))
  };
  const submitButton = orderForm.querySelector('button[type="submit"]');
  orderSubmissionInProgress = true;
  submitButton.disabled = true;
  orderMessage.textContent = 'Saving your order...';
  orderMessage.style.color = '';

  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Order failed');
    }

    const whatsappLink = document.createElement('a');
    whatsappLink.href = data.whatsapp_url;
    whatsappLink.target = '_blank';
    whatsappLink.rel = 'noopener noreferrer';
    whatsappLink.className = 'whatsapp-btn';
    whatsappLink.textContent = 'Send Order to SFF on WhatsApp';
    orderMessage.replaceChildren(
      document.createTextNode(
        `Order placed successfully! Order #${data.order_id} — Total: ${formatPrice(data.total)}. WhatsApp will open when you press the button; press Send there to send your order. `
      ),
      whatsappLink
    );
    orderMessage.style.color = '#2e7d32';
    state.cart = [];
    renderCart();
    orderForm.reset();
  } catch (error) {
    orderMessage.textContent = `Could not save the order: ${error.message}. Please try again.`;
    orderMessage.style.color = '#c0392b';
  } finally {
    orderSubmissionInProgress = false;
    submitButton.disabled = false;
  }
});

loadProducts();
renderCart();
