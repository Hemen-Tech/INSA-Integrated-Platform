const languageSwitcher = document.getElementById('languageSwitcher');
const page = document.body.dataset.page; // "index" for this page
let currentLang = localStorage.getItem('lang') || 'en';

async function loadLanguage(lang) {
    const res = await fetch(`lang/${lang}.json`);
    const translations = await res.json();
    const pageTranslations = translations[page] || {};

    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        const translation = pageTranslations[key] ||
            (translations.platform && translations.platform[key]);
        if (translation) el.textContent = translation;
    });

    localStorage.setItem('lang', lang);
    if(languageSwitcher) languageSwitcher.value = lang;
}

// Load on page start
loadLanguage(currentLang);

// Dropdown change
if(languageSwitcher) {
    languageSwitcher.value = currentLang;
    languageSwitcher.addEventListener('change', (e) => {
        loadLanguage(e.target.value);
    });
}
