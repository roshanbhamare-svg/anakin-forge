const API_URL = 'http://localhost:8000/api';

// --- Shared Persistent State ---
let comparisonProducts = JSON.parse(localStorage.getItem('shopagent_comparison')) || [];
let trackedProducts = JSON.parse(localStorage.getItem('shopagent_watchlist')) || [];
let lastSearchProducts = {}; // In-memory map of id -> product object

// --- Navigation ---
const navLinks = document.querySelectorAll('.nav-links li');
const viewSections = document.querySelectorAll('.view-section');

// Initialize compare badge
updateCompareCount();

navLinks.forEach(link => {
    link.addEventListener('click', () => {
        navLinks.forEach(l => l.classList.remove('active'));
        link.classList.add('active');
        
        const viewId = link.getAttribute('data-view');
        viewSections.forEach(sec => sec.classList.remove('active'));
        document.getElementById(`view-${viewId}`).classList.add('active');
        
        if(viewId === 'watchlist') renderWatchlist();
        if(viewId === 'compare') generateCompare();
        if(viewId === 'profile') fetchProfile();
    });
});

// --- Search / Chat ---
const form = document.getElementById('promptForm');
const input = document.getElementById('promptInput');
const chatArea = document.getElementById('chatArea');
const submitBtn = document.getElementById('submitBtn');
const timeline = document.getElementById('activityTimeline');

function updateCompareCount() {
    document.getElementById('compareCount').textContent = comparisonProducts.length;
}

function addMessage(text, isUser = false) {
    const msg = document.createElement('div');
    msg.className = `message ${isUser ? 'user-message' : 'ai-message'}`;
    msg.innerHTML = `
        <div class="avatar"><i class="ph ${isUser ? 'ph-user' : 'ph-robot'}"></i></div>
        <div class="message-content">${text}</div>
    `;
    chatArea.appendChild(msg);
    chatArea.scrollTop = chatArea.scrollHeight;
    return msg;
}

function addTimelineEvent(text) {
    if(timeline.querySelector('.timeline-empty')) {
        timeline.innerHTML = '';
    }
    const ev = document.createElement('div');
    ev.className = 'timeline-item';
    ev.innerHTML = `
        <div class="timeline-icon"><i class="ph ph-check-circle"></i></div>
        <div>${text}</div>
    `;
    timeline.appendChild(ev);
    timeline.scrollTop = timeline.scrollHeight;
}

function renderProducts(products, requirements, isLive) {
    const modeLabel = isLive ? '' : ' <span style="font-size:0.75rem; color:#f59e0b; background:rgba(245,158,11,0.1); padding:2px 8px; border-radius:4px;">⚠ Demo Data — Not Live Prices</span>';
    let html = `<p>Found ${products.length} verified product(s) matching your criteria.${modeLabel}</p>
                <div class="products-grid">`;
                
    products.forEach(p => {
        lastSearchProducts[p.id] = p; // store full product object
        const specs = p.specifications || {};
        const src = p.source;
        const verified = p.verification || {};
        const checkedAt = src ? new Date(src.retrieved_at).toLocaleTimeString() : null;
        const priceLabel = verified.price 
            ? `<span style="font-size:0.75rem; color:var(--success-color); margin-left:6px;">✓ Price verified ${checkedAt ? '· ' + checkedAt : ''}</span>`
            : `<span style="font-size:0.75rem; color:#f59e0b; margin-left:6px;">⚠ Demo price (not live)</span>`;
        const confidence = p.confidence || 'unverified';
        const confColor = confidence === 'verified' ? 'var(--success-color)' : confidence === 'partially_verified' ? '#60a5fa' : '#f59e0b';
        const specsList = [specs.processor, specs.ram, specs.gpu, specs.weight].filter(Boolean);
        const viewBtn = p.url && !p.url.includes('/mock/')
            ? `<a href="${p.url}" target="_blank" class="action-btn secondary-btn" style="text-decoration:none; text-align:center;"><i class="ph ph-arrow-square-out"></i> View</a>`
            : '';
        html += `
            <div class="glass-card product-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <h3 style="flex:1;">${p.title}</h3>
                    <span style="font-size:0.7rem; color:${confColor}; white-space:nowrap; margin-left:8px; padding:2px 6px; border:1px solid ${confColor}; border-radius:4px;">${confidence}</span>
                </div>
                <div class="product-price">₹${p.price.toLocaleString('en-IN')} ${priceLabel}</div>
                <div style="font-size:0.8rem; color:var(--text-muted); margin-bottom:5px;">📍 ${p.store || 'Unknown Store'}</div>
                <div class="product-specs">${specsList.map(s => `<span>${s}</span>`).join('') || '<span>Specs not parsed</span>'}</div>
                <div class="product-reason">${p.matchReason || ''}</div>
                <div class="card-actions">
                    <button class="action-btn secondary-btn" onclick="addToCompare('${p.id}')">
                        <i class="ph ph-scales"></i> Compare
                    </button>
                    <button class="action-btn primary-btn" onclick="trackProduct('${p.id}')">
                        <i class="ph ph-bell"></i> Track
                    </button>
                    ${viewBtn}
                </div>
            </div>
        `;
    });
    
    html += `</div>`;
    addMessage(html, false);
}

form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const prompt = input.value.trim();
    if (!prompt) return;

    input.value = '';
    input.disabled = true;
    submitBtn.disabled = true;

    addMessage(prompt, true);
    timeline.innerHTML = ''; // reset timeline
    addTimelineEvent("Started processing request");
    
    const indicatorMsg = addMessage(`
        <div class="typing-indicator" id="streamingIndicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `);

    try {
        const response = await fetch(`${API_URL}/find-laptops`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ prompt: prompt })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let done = false;

        while (!done) {
            const { value, done: doneReading } = await reader.read();
            done = doneReading;
            
            if (value) {
                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\\n');
                
                for (let line of lines) {
                    if (line.trim()) {
                        try {
                            const data = JSON.parse(line);
                            if (data.type === "status") {
                                addTimelineEvent(`[${data.layer}] ${data.status}`);
                            } else if (data.type === "error") {
                                if (indicatorMsg && indicatorMsg.parentNode) indicatorMsg.remove();
                                addTimelineEvent(`[Error] ${data.message}`);
                                addMessage(`<span style="color:var(--danger-color)">Error: ${data.message}</span>`);
                                return;
                            } else if (data.type === "products") {
                                if (indicatorMsg && indicatorMsg.parentNode) indicatorMsg.remove();
                                renderProducts(data.products, data.requirements, data.is_live);
                            }
                        } catch (e) {
                            console.error("Parse error:", line);
                        }
                    }
                }
            }
        }
    } catch (error) {
        if (indicatorMsg && indicatorMsg.parentNode) indicatorMsg.remove();
        addMessage(`<span style="color:var(--danger-color)">Error connecting to agent.</span>`);
    } finally {
        input.disabled = false;
        submitBtn.disabled = false;
        input.focus();
        addTimelineEvent("Task complete.");
    }
});

// --- Compare ---
window.addToCompare = function(id) {
    const product = lastSearchProducts[id];
    if (!product) return;
    
    if (!comparisonProducts.some(p => p.id === id)) {
        comparisonProducts.push(product);
        localStorage.setItem('shopagent_comparison', JSON.stringify(comparisonProducts));
        showToast("Added to comparison");
        updateCompareCount();
        
        if (document.getElementById('view-compare').classList.contains('active')) {
            generateCompare();
        }
    } else {
        showToast("Product is already in comparison");
    }
}

async function generateCompare() {
    const content = document.getElementById('compareContent');
    if (comparisonProducts.length < 2) {
        let msg = `<div class="empty-state"><p>Please select at least 2 products to compare.</p></div>`;
        if (comparisonProducts.length === 1) {
            msg = `<div class="empty-state"><p>Currently selected: <b>${comparisonProducts[0].title}</b>.<br><br>Select one more product to view comparison.</p>
            <button onclick="removeFromCompare('${comparisonProducts[0].id}')" style="margin-top:10px; padding:8px 15px; border-radius:4px; border:none; background:var(--danger-color); color:white; cursor:pointer;">Remove</button>
            </div>`;
        }
        content.innerHTML = msg;
        return;
    }
    
    content.innerHTML = `<div style="text-align:center; padding:20px;">Analyzing specifications...</div>`;
    
    try {
        const productModels = comparisonProducts.map(p => p.model);
        const res = await fetch(`${API_URL}/compare`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ productIds: productModels })
        });
        const aiAnalysis = await res.json();
        
        let html = `
            <div class="ai-recommendation-box" style="margin-bottom: 20px;">
                <h3><i class="ph ph-sparkle"></i> AI Recommendation</h3>
                <p>${aiAnalysis.recommendation}</p>
                <div style="display:flex; gap:15px; margin-top:10px; font-size:0.9rem;">
                    <div><strong>Best Overall:</strong> ${aiAnalysis.bestOverall}</div>
                    <div><strong>Best Value:</strong> ${aiAnalysis.bestValue}</div>
                </div>
            </div>
        `;
        
        let tableHtml = `<div style="overflow-x:auto;">
            <table class="compare-table">
            <tr>
                <th>Feature</th>
                ${comparisonProducts.map(p => `<th>
                    <div style="display:flex; flex-direction:column; justify-content:space-between; height:100%;">
                        <div>${p.title}</div>
                        <button onclick="removeFromCompare('${p.id}')" style="margin-top:10px; padding:5px; font-size:0.8rem; border-radius:4px; border:none; background:var(--danger-color); color:white; cursor:pointer;">Remove</button>
                    </div>
                </th>`).join('')}
            </tr>
            <tr>
                <td>Price</td>
                ${comparisonProducts.map(p => `<td style="color:var(--success-color); font-weight:bold;">₹${p.price.toLocaleString()}</td>`).join('')}
            </tr>
            <tr>
                <td>Store</td>
                ${comparisonProducts.map(p => `<td>${p.store}</td>`).join('')}
            </tr>
            <tr>
                <td>Processor</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.processor || '-'}</td>`).join('')}
            </tr>
            <tr>
                <td>GPU</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.gpu || '-'}</td>`).join('')}
            </tr>
            <tr>
                <td>RAM</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.ram || '-'}</td>`).join('')}
            </tr>
            <tr>
                <td>Storage</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.storage || '-'}</td>`).join('')}
            </tr>
            <tr>
                <td>Display</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.display || '-'}</td>`).join('')}
            </tr>
            <tr>
                <td>Weight</td>
                ${comparisonProducts.map(p => `<td>${p.specifications.weight || '-'}</td>`).join('')}
            </tr>
        </table></div>`;
        
        content.innerHTML = html + tableHtml;
        
    } catch(e) {
        content.innerHTML = `<p>Error generating comparison.</p>`;
    }
}

window.removeFromCompare = function(id) {
    comparisonProducts = comparisonProducts.filter(p => p.id !== id);
    localStorage.setItem('shopagent_comparison', JSON.stringify(comparisonProducts));
    updateCompareCount();
    generateCompare();
    showToast("Removed from comparison");
}

// --- Watchlist ---
window.trackProduct = function(id) {
    const product = lastSearchProducts[id];
    if (!product) return;
    
    const target = prompt(`Current price is ₹${product.price.toLocaleString('en-IN')}.\n\nEnter target price to alert you:`, product.price - 5000);
    if (!target) return;
    
    const targetPrice = parseInt(target);
    if(isNaN(targetPrice)) {
        showToast('Invalid price entered.');
        return;
    }
    
    const trackObj = {
        productId: product.id,
        product: product,
        targetPrice: targetPrice,
        currentPrice: product.price,
        status: 'watching'
    };
    
    const existingIdx = trackedProducts.findIndex(t => t.productId === product.id);
    if (existingIdx >= 0) {
        trackedProducts[existingIdx] = trackObj;
    } else {
        trackedProducts.push(trackObj);
    }
    
    localStorage.setItem('shopagent_watchlist', JSON.stringify(trackedProducts));
    showToast('Added to Watchlist! Price will be monitored.');
}

function renderWatchlist() {
    const content = document.getElementById('watchlistContent');
    
    if (trackedProducts.length === 0) {
        content.innerHTML = `<div class="empty-state"><i class="ph ph-bell" style="font-size: 4rem; color: var(--text-muted);"></i><p>You aren't tracking any products yet.</p></div>`;
        return;
    }
    
    let html = ``;
    trackedProducts.forEach(t => {
        const isReached = t.currentPrice <= t.targetPrice;
        let statusBadge = isReached ? 
            `<span style="color:var(--success-color); font-weight:bold;"><i class="ph ph-check-circle"></i> Target Price Reached</span>` : 
            `<span style="color:var(--text-muted)"><i class="ph ph-eyes"></i> Watching</span>`;
            
        let cardBorder = isReached ? `border: 1px solid var(--success-color); background: rgba(16, 185, 129, 0.1);` : ``;
            
        html += `
            <div class="glass-card track-card" style="${cardBorder}">
                <div>
                    <h3>${t.product.title}</h3>
                    <p style="color:var(--text-muted); font-size:0.95rem; margin-top:8px;">
                        Current Price: <strong style="color: ${isReached ? 'var(--success-color)' : 'var(--text-color)'}">₹${t.currentPrice.toLocaleString()}</strong><br>
                        Target Price: <strong>₹${t.targetPrice.toLocaleString()}</strong>
                    </p>
                    <p style="font-size:0.85rem; color:var(--text-muted); margin-top:5px;">Store: ${t.product.store}</p>
                </div>
                <div style="display:flex; flex-direction:column; align-items:flex-end; gap:10px;">
                    ${statusBadge}
                    <button onclick="removeFromWatchlist('${t.productId}')" style="padding:6px 12px; font-size:0.85rem; border-radius:4px; border:none; background:var(--danger-color); color:white; cursor:pointer;"><i class="ph ph-trash"></i> Remove</button>
                </div>
            </div>
        `;
    });
    content.innerHTML = html;
}

window.removeFromWatchlist = function(id) {
    trackedProducts = trackedProducts.filter(t => t.productId !== id);
    localStorage.setItem('shopagent_watchlist', JSON.stringify(trackedProducts));
    renderWatchlist();
    showToast("Removed from Watchlist");
}

document.getElementById('demoPriceDropBtn').addEventListener('click', () => {
    if (trackedProducts.length === 0) {
        showToast('No products tracked yet. Track a product first.');
        return;
    }
    let triggered = false;
    trackedProducts.forEach(t => {
        if (t.currentPrice > t.targetPrice) {
            // Drop price by ~10% or to target - 100, whichever is lower
            t.currentPrice = t.targetPrice - 100;
            t.status = 'reached';
            triggered = true;
        }
    });
    
    if (triggered) {
        localStorage.setItem('shopagent_watchlist', JSON.stringify(trackedProducts));
        renderWatchlist();
        showToast('🎉 [Demo] Price drop simulated! Target reached.');
    } else {
        showToast('All tracked products already at or below target.');
    }
});

// --- Profile ---
async function fetchProfile() {
    const content = document.getElementById('profileContent');
    try {
        const res = await fetch(`${API_URL}/profile`);
        const data = await res.json();
        
        content.innerHTML = `
            <div class="glass-card">
                <p>These preferences are learned automatically from your chats.</p>
                <hr style="border-color:var(--glass-border); margin:15px 0;">
                <h3>Budget Sensitivity</h3>
                <p style="color:var(--text-muted); margin-bottom:10px;">${data.profile.budgetPreference}</p>
                
                <h3>Minimum RAM</h3>
                <p style="color:var(--text-muted); margin-bottom:10px;">${data.profile.minimumRam || 'Not specified'}</p>
                
                <h3>Avoid</h3>
                <div class="tags">
                    ${data.profile.avoid.length ? data.profile.avoid.map(a => `<span class="tag">${a}</span>`).join('') : '<span style="color:var(--text-muted)">None</span>'}
                </div>
            </div>
        `;
    } catch(e) {}
}

// --- Utils ---
function showToast(msg) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<i class="ph ph-info toast-icon"></i> <div>${msg}</div>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}
