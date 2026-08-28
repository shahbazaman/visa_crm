/**
 * visa_crm/public/js/crm_spa_redirect.js
 *
 * WhatsApp Web Launcher & Native CRM Enhancements.
 * Ensures the 'WhatsApp' sidebar launcher is present in Frappe CRM sidebar
 * and opens https://web.whatsapp.com/ in a new browser tab.
 */

(function () {
  'use strict';

  function initWhatsAppSidebarLauncher() {
    // Check if already injected
    if (document.getElementById('crm-sidebar-whatsapp-launcher')) return;

    // Find the CRM navigation container (views list)
    const navLists = document.querySelectorAll('nav.flex.flex-col');
    if (!navLists || !navLists.length) return;

    // Find the main views navigation (contains Leads, Deals, Call Logs)
    let targetNav = null;
    let callLogsBtn = null;

    for (const nav of navLists) {
      const buttons = nav.querySelectorAll('button');
      for (const btn of buttons) {
        const text = (btn.innerText || '').trim();
        if (text === 'Call Logs' || text === 'Call Log' || btn.textContent.includes('Call Logs')) {
          targetNav = nav;
          callLogsBtn = btn;
          break;
        }
      }
      if (callLogsBtn) break;
    }

    if (!targetNav || !callLogsBtn) return;

    // Check if WhatsApp button already exists in targetNav
    const existingWA = Array.from(targetNav.querySelectorAll('button')).some(
      btn => (btn.innerText || '').trim() === 'WhatsApp'
    );
    if (existingWA) return;

    // Create the WhatsApp sidebar button matching exact SidebarLink styling
    const waBtn = document.createElement('button');
    waBtn.id = 'crm-sidebar-whatsapp-launcher';
    waBtn.className = 'flex h-7.5 cursor-pointer items-center rounded text-ink-gray-8 duration-300 ease-in-out hover:bg-surface-gray-2 focus:outline-none focus:transition-none focus-visible:rounded focus-visible:ring-2 focus-visible:ring-outline-gray-3 mx-2 my-[1.5px]';
    waBtn.setAttribute('type', 'button');
    waBtn.setAttribute('title', 'WhatsApp');

    // WhatsApp SVG icon matching WhatsAppIcon.vue
    const svgIcon = `
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" class="flex items-center size-4 text-ink-gray-8">
        <path d="M4.19429 13.6C5.56327 14.5333 8.15223 15.1961 9.73933 14.8099C11.3264 14.4238 12.7265 13.4706 13.6872 12.1223C14.6479 10.7739 15.1061 9.11889 14.9793 7.45557C14.8524 5.79226 14.1487 4.22998 12.9952 3.05026C11.8416 1.87055 10.3139 1.15098 8.68746 1.02121C7.061 0.891454 5.4427 1.36004 4.12418 2.34253C2.80566 3.32502 1.87363 4.7568 1.49604 6.37987C1.11846 8.00294 1.45633 10.3333 2.36898 11.7333L1 15L4.19429 13.6Z" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"/>
        <path fill-rule="evenodd" clip-rule="evenodd" d="M8.71612 10.4723L9.28571 9.71429C9.70194 9.29806 9.94789 9.46347 10.5197 9.69365C10.5539 9.70744 10.5864 9.72549 10.616 9.74759L10.8769 9.94262C11.0372 10.056 11.0417 10.2914 10.8858 10.4108L10.3234 10.8417C10.0967 11.0153 9.79336 11.0518 9.53832 10.9229C8.90412 10.6023 7.67975 9.92002 6.81142 9.04152C5.9706 8.19086 5.36418 7.06182 5.06827 6.44175C4.93712 6.16692 5.00025 5.84477 5.21201 5.62529L5.7289 5.08958C5.86084 4.95283 6.08682 4.97592 6.18808 5.13648L6.53726 5.62529C6.81142 6.0633 6.42128 6.43691 6.18808 6.59294L5.42857 7.13786" fill="currentColor"/>
        <path d="M8.71612 10.4723L9.28571 9.71429C9.70194 9.29806 9.94789 9.46347 10.5197 9.69365C10.5539 9.70744 10.5864 9.72549 10.616 9.74759L10.8769 9.94262C11.0372 10.056 11.0417 10.2914 10.8858 10.4108L10.3234 10.8417C10.0967 11.0153 9.79336 11.0518 9.53832 10.9229C8.90412 10.6023 7.67975 9.92002 6.81142 9.04152C5.9706 8.19086 5.36418 7.06182 5.06827 6.44175C4.93712 6.16692 5.00025 5.84477 5.21201 5.62529L5.7289 5.08958C5.86084 4.95283 6.08682 4.97592 6.18808 5.13648L6.53726 5.62529C6.81142 6.0633 6.42128 6.43691 6.18808 6.59294L5.42857 7.13786" stroke="currentColor" stroke-linejoin="round"/>
      </svg>
    `;

    waBtn.innerHTML = `
      <div class="flex w-full items-center justify-between duration-300 ease-in-out px-2 py-[7px]">
        <div class="flex items-center truncate">
          ${svgIcon}
          <span class="flex-1 flex-shrink-0 truncate text-sm duration-300 ease-in-out ml-2 w-auto opacity-100 font-normal">
            WhatsApp
          </span>
        </div>
      </div>
    `;

    // Click behavior: Navigate to /crm/whatsapp
    waBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (window.location.pathname !== '/crm/whatsapp') {
        try {
          // Use Vue router if available
          const appElement = document.querySelector('#app');
          if (appElement && appElement.__vue_app__ && appElement.__vue_app__.config.globalProperties.$router) {
            appElement.__vue_app__.config.globalProperties.$router.push({ name: 'WhatsApp' });
            return;
          }
        } catch (err) {}
        window.location.href = '/crm/whatsapp';
      }
    });

    // Insert right after Call Logs
    callLogsBtn.insertAdjacentElement('afterend', waBtn);
  }

  // Setup MutationObserver to detect sidebar mount & route transitions
  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => {
        initWhatsAppSidebarLauncher();
      });
    } else {
      initWhatsAppSidebarLauncher();
    }

    const observer = new MutationObserver(() => {
      initWhatsAppSidebarLauncher();
    });

    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
  }
})();
