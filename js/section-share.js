/**
 * Section Share
 * Adds a copy-link control to section headings that have an id.
 */
(function () {
    'use strict';

    var LINK_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M10 13a5 5 0 0 0 7.54.54l1.42-1.42a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54L5.04 11.88a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>';

    function sectionUrl(id) {
        return window.location.origin + window.location.pathname + window.location.search + '#' + id;
    }

    function copyText(text) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text);
        }

        return new Promise(function (resolve, reject) {
            var input = document.createElement('textarea');
            input.value = text;
            input.setAttribute('readonly', '');
            input.style.position = 'absolute';
            input.style.left = '-9999px';
            document.body.appendChild(input);
            input.select();
            try {
                if (!document.execCommand('copy')) {
                    throw new Error('Copy command failed');
                }
                resolve();
            } catch (err) {
                reject(err);
            } finally {
                document.body.removeChild(input);
            }
        });
    }

    function showCopied(link) {
        var feedback = link.querySelector('.section-share-feedback');
        link.classList.add('is-copied');
        link.setAttribute('aria-label', 'Link copied');
        if (feedback) {
            feedback.hidden = false;
        }

        window.setTimeout(function () {
            link.classList.remove('is-copied');
            link.setAttribute('aria-label', link.dataset.label);
            if (feedback) {
                feedback.hidden = true;
            }
        }, 1800);
    }

    function enhanceHeading(heading) {
        var id = heading.id;
        if (!id || heading.querySelector('.section-share')) {
            return;
        }

        var title = heading.textContent.replace(/\s+/g, ' ').trim() || 'this section';
        var label = 'Copy link to ' + title;
        var link = document.createElement('a');
        link.className = 'section-share';
        link.href = '#' + id;
        link.dataset.label = label;
        link.setAttribute('aria-label', label);
        link.setAttribute('title', 'Copy link to this section');
        link.innerHTML = LINK_ICON + '<span class="section-share-feedback" role="status" aria-live="polite" hidden>Copied</span>';

        link.addEventListener('click', function (event) {
            event.preventDefault();
            var url = sectionUrl(id);

            if (history.replaceState) {
                history.replaceState(null, '', '#' + id);
            } else {
                window.location.hash = id;
            }

            heading.scrollIntoView({ behavior: 'smooth', block: 'start' });

            copyText(url).then(function () {
                showCopied(link);
            }).catch(function () {
                window.prompt('Copy this link:', url);
            });
        });

        heading.appendChild(link);
    }

    function init() {
        document.querySelectorAll('article h2[id]').forEach(enhanceHeading);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
