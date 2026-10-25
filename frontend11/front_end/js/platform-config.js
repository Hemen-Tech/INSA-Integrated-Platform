// Set INSA_PLATFORM_CONFIG before this script to override these local defaults.
const platformConfig = window.INSA_PLATFORM_CONFIG || {};
const probeHomeUrl = platformConfig.probeUrl || 'http://localhost:3000/';
const droughtUrl = platformConfig.droughtUrl || 'http://localhost:5501/';
const pnisUrl = platformConfig.pnisUrl || 'http://localhost:8503/';

document.querySelectorAll('[data-probe-home]').forEach((link) => {
    link.href = probeHomeUrl;
});

const platformNav = document.querySelector('#sidebar .nav');
if (platformNav && !platformNav.querySelector('[data-platform-modules]')) {
    const divider = document.createElement('div');
    divider.className = 'platform-nav-divider';
    divider.setAttribute('role', 'separator');
    divider.setAttribute('data-platform-modules', '');

    const droughtLink = document.createElement('a');
    droughtLink.href = droughtUrl;
    droughtLink.className = 'nav-link';
    droughtLink.setAttribute('aria-current', 'page');
    droughtLink.innerHTML = '<i class="fas fa-cloud-sun" aria-hidden="true"></i><span data-i18n="drought_module">Drought Intelligence</span>';

    const pnisLink = document.createElement('a');
    pnisLink.href = pnisUrl;
    pnisLink.className = 'nav-link';
    pnisLink.target = '_blank';
    pnisLink.rel = 'noopener noreferrer';
    pnisLink.innerHTML = '<i class="fas fa-route" aria-hidden="true"></i><span data-i18n="pnis_module">PNIS · In Development</span>';

    platformNav.append(divider, droughtLink, pnisLink);
}

const mainContent = document.querySelector('.main-content');
if (mainContent && !mainContent.querySelector('[data-simulation-notice]')) {
    const notice = document.createElement('p');
    notice.className = 'platform-data-notice';
    notice.setAttribute('data-simulation-notice', '');
    notice.setAttribute('data-i18n', 'simulation_notice');
    notice.textContent = 'Dashboard metrics and generated forecast outputs are simulated, not validated live predictions.';
    mainContent.prepend(notice);
}
