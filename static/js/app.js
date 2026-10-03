/* BotBuilder Dynamic Interactivity */

document.addEventListener('DOMContentLoaded', () => {
    // Copy link helper
    const copyBtns = document.querySelectorAll('.btn-copy');
    copyBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const targetId = btn.getAttribute('data-copy-target');
            const targetEl = document.getElementById(targetId);
            if (targetEl) {
                const textToCopy = targetEl.value || targetEl.innerText;
                navigator.clipboard.writeText(textToCopy.trim()).then(() => {
                    const originalText = btn.innerHTML;
                    btn.innerHTML = '✓ Copied!';
                    btn.style.opacity = '0.8';
                    setTimeout(() => {
                        btn.innerHTML = originalText;
                        btn.style.opacity = '1';
                    }, 2000);
                });
            }
        });
    });
});

// Dynamic Service Row Helper for Create & Edit forms
function addServiceRow(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const rowCount = container.children.length;
    const rowDiv = document.createElement('div');
    rowDiv.className = 'grid-3 service-row form-group';
    rowDiv.style.alignItems = 'end';
    rowDiv.innerHTML = `
        <div>
            <label class="form-label">Service Name</label>
            <input type="text" name="service_name[]" class="form-control" placeholder="e.g. Teeth Cleaning" required>
        </div>
        <div>
            <label class="form-label">Price</label>
            <input type="text" name="service_price[]" class="form-control" placeholder="e.g. $80">
        </div>
        <div style="display: flex; gap: 0.5rem;">
            <div style="flex: 1;">
                <label class="form-label">Details (optional)</label>
                <input type="text" name="service_details[]" class="form-control" placeholder="e.g. 30 mins session">
            </div>
            <button type="button" class="btn btn-danger btn-sm" onclick="this.closest('.service-row').remove()">✕</button>
        </div>
    `;
    container.appendChild(rowDiv);
}

// Add new FAQ item dynamically on Review page
function addReviewFAQRow(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const newId = Date.now();
    const faqCard = document.createElement('div');
    faqCard.className = 'faq-edit-card';
    faqCard.id = `faq-card-${newId}`;
    faqCard.innerHTML = `
        <div class="faq-card-header">
            <span class="badge badge-warning">New Draft FAQ</span>
            <button type="button" class="btn btn-danger btn-sm" onclick="this.closest('.faq-edit-card').remove()">Delete</button>
        </div>
        <div class="form-group">
            <label class="form-label">Question</label>
            <input type="text" name="faq_q_${newId}" class="form-control" placeholder="Enter question..." required>
        </div>
        <div class="form-group">
            <label class="form-label">Alternative Phrasings (comma separated)</label>
            <input type="text" name="faq_alt_${newId}" class="form-control" placeholder="e.g. price list, cost of services">
        </div>
        <div class="form-group">
            <label class="form-label">Answer</label>
            <textarea name="faq_a_${newId}" class="form-control" rows="2" placeholder="Enter full answer..." required></textarea>
        </div>
        <div class="grid-2">
            <div class="form-group">
                <label class="form-label">Button Label (max 20 chars)</label>
                <input type="text" name="faq_button_label_${newId}" class="form-control" placeholder="Button text">
            </div>
            <div class="form-group" style="display: flex; align-items: center; gap: 0.5rem; margin-top: 1.5rem;">
                <input type="checkbox" name="faq_show_button_${newId}" value="true" checked id="show_btn_${newId}">
                <label for="show_btn_${newId}" class="form-label" style="margin: 0; cursor: pointer;">Show as Menu Button</label>
            </div>
        </div>
        <input type="hidden" name="faq_ids[]" value="${newId}">
    `;
    container.appendChild(faqCard);
}
