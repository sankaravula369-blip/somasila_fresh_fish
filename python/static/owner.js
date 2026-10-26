const ownerMessage = document.getElementById('owner-message');
const ownerOrders = document.getElementById('owner-orders');
const deliveryStatuses = ['Pending', 'Out for delivery', 'Delivered'];

function formatPrice(value) {
  return `₹${Number(value).toFixed(2)}`;
}

async function updateStatus(orderId, status, button) {
  button.disabled = true;

  try {
    const response = await fetch(`/api/owner/orders/${orderId}/status`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || 'Unable to update delivery status');
    }

    ownerMessage.textContent = `Order #${orderId} updated to ${result.status}.`;
    await loadOrders();
  } catch (error) {
    ownerMessage.textContent = error.message;
    button.disabled = false;
  }
}

function renderOrders(orders) {
  ownerOrders.replaceChildren();

  for (const order of orders) {
    const card = document.createElement('article');
    card.className = 'owner-order-card';

    const title = document.createElement('h2');
    title.textContent = `Order #${order.id} — ${order.customer}`;
    const phone = document.createElement('p');
    phone.textContent = `Phone: ${order.phone}`;
    const address = document.createElement('p');
    address.textContent = `Delivery address: ${order.address}`;
    const items = document.createElement('ul');
    items.className = 'owner-order-items';
    for (const item of order.items) {
      const entry = document.createElement('li');
      entry.textContent = `${item.name} x ${item.qty} — ${formatPrice(item.subtotal)}`;
      items.append(entry);
    }
    const total = document.createElement('p');
    total.textContent = `Total: ${formatPrice(order.total)}`;
    const statusRow = document.createElement('div');
    statusRow.className = 'owner-order-status';
    const statusLabel = document.createElement('label');
    statusLabel.textContent = 'Delivery status: ';
    const select = document.createElement('select');
    select.setAttribute('aria-label', `Delivery status for order ${order.id}`);
    for (const status of deliveryStatuses) {
      const option = document.createElement('option');
      option.value = status;
      option.textContent = status;
      option.selected = status === order.status;
      select.append(option);
    }
    statusLabel.append(select);
    const button = document.createElement('button');
    button.className = 'btn';
    button.type = 'button';
    button.textContent = 'Update status';
    button.addEventListener('click', () => updateStatus(order.id, select.value, button));
    statusRow.append(statusLabel, button);
    card.append(title, phone, address, items, total, statusRow);
    ownerOrders.append(card);
  }
}

async function loadOrders() {
  try {
    const response = await fetch('/api/owner/orders');
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || 'Unable to load orders');
    }

    if (data.length === 0) {
      ownerMessage.textContent = 'No customer orders yet.';
      ownerOrders.replaceChildren();
      return;
    }

    ownerMessage.textContent = `${data.length} order${data.length === 1 ? '' : 's'}.`;
    renderOrders(data);
  } catch (error) {
    ownerMessage.textContent = error.message;
  }
}

loadOrders();
