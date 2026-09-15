/**
 * Progress Blog
 * Groups posts by month, defers off-month media, and replaces YouTube
 * iframes with click-to-play thumbnails so the page does not load every
 * post, image, and video at once.
 */
(function () {
    'use strict';

    var MONTH_NAMES = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ];

    var posts = [];
    var months = [];
    var activeMonth = '';
    var searchQuery = '';
    var postsEl;
    var controlsEl;

    function parsePostDate(text) {
        var match = String(text || '').match(/([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})/);
        if (!match) {
            return null;
        }

        var monthIndex = MONTH_NAMES.findIndex(function (name) {
            return name.toLowerCase() === match[1].toLowerCase();
        });
        if (monthIndex < 0) {
            return null;
        }

        var day = parseInt(match[2], 10);
        var year = parseInt(match[3], 10);
        var iso = year + '-' + String(monthIndex + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');

        return {
            year: year,
            month: monthIndex,
            day: day,
            iso: iso,
            monthKey: iso.slice(0, 7),
            monthLabel: MONTH_NAMES[monthIndex] + ' ' + year
        };
    }

    function youtubeIdFromSrc(src) {
        var match = String(src || '').match(/(?:youtube(?:-nocookie)?\.com\/embed\/|youtu\.be\/)([A-Za-z0-9_-]{11})/);
        return match ? match[1] : null;
    }

    function createLiteYouTube(videoId, title, options) {
        var lite = document.createElement('button');
        lite.type = 'button';
        lite.className = 'yt-lite' + (options && options.vertical ? ' yt-lite-short' : '');
        lite.setAttribute('data-youtube-id', videoId);
        if (options && options.vertical) {
            lite.setAttribute('data-aspect', '9/16');
        }
        lite.setAttribute('aria-label', 'Play video: ' + title);

        var thumb = document.createElement('img');
        thumb.alt = '';
        thumb.loading = 'lazy';
        thumb.decoding = 'async';
        thumb.src = 'https://i.ytimg.com/vi/' + videoId + '/hqdefault.jpg';

        var play = document.createElement('span');
        play.className = 'yt-lite-play';
        play.setAttribute('aria-hidden', 'true');

        lite.appendChild(thumb);
        lite.appendChild(play);
        lite.addEventListener('click', function () {
            playYouTube(lite, title);
        });
        return lite;
    }

    function isVerticalEmbed(iframe, wrap) {
        if (iframe && iframe.closest && iframe.closest('.blog-post-video-short')) {
            return true;
        }
        if (!wrap || !wrap.style) {
            return false;
        }
        var paddingBottom = wrap.style.paddingBottom || '';
        var value = parseFloat(paddingBottom);
        return paddingBottom.indexOf('%') !== -1 && value > 100;
    }

    function replaceIframeWithLite(iframe) {
        var src = iframe.getAttribute('src') || iframe.getAttribute('data-src') || '';
        iframe.removeAttribute('src');

        var videoId = youtubeIdFromSrc(src);
        if (!videoId) {
            iframe.removeAttribute('src');
            return;
        }

        var title = iframe.getAttribute('title') || 'Play video';
        var wrap = iframe.parentNode;
        var vertical = isVerticalEmbed(iframe, wrap);
        var lite = createLiteYouTube(videoId, title, { vertical: vertical });

        if (wrap && wrap.children.length === 1 && wrap.style && wrap.style.paddingBottom) {
            wrap.parentNode.replaceChild(lite, wrap);
        } else {
            iframe.parentNode.replaceChild(lite, iframe);
        }
    }

    function enableLiteYouTube(postEl) {
        postEl.querySelectorAll('.blog-post-video iframe').forEach(replaceIframeWithLite);
    }

    function playYouTube(lite, title) {
        var videoId = lite.getAttribute('data-youtube-id');
        if (!videoId) {
            return;
        }

        var vertical = lite.classList.contains('yt-lite-short') ||
            lite.getAttribute('data-aspect') === '9/16' ||
            !!(lite.closest && lite.closest('.blog-post-video-short'));
        var wrap = document.createElement('div');
        wrap.style.cssText = vertical
            ? 'position:relative;width:100%;max-width:280px;height:0;padding-bottom:177.78%;margin-left:auto;margin-right:auto;'
            : 'position:relative;width:100%;height:0;padding-bottom:56.25%;';

        var iframe = document.createElement('iframe');
        iframe.src = 'https://www.youtube-nocookie.com/embed/' + videoId + '?autoplay=1';
        iframe.title = title || 'YouTube video';
        iframe.setAttribute('allow', 'accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture');
        iframe.setAttribute('allowfullscreen', '');
        iframe.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;';

        wrap.appendChild(iframe);
        lite.parentNode.replaceChild(wrap, lite);
    }

    function stopPlayingVideos(scope) {
        (scope || postsEl).querySelectorAll('.blog-post-video iframe').forEach(function (iframe) {
            var postEl = iframe.closest('.blog-post');
            if (postEl) {
                enableLiteYouTube(postEl);
            }
        });

        (scope || postsEl).querySelectorAll('video').forEach(function (video) {
            video.pause();
        });
    }

    function deferTumblrEmbed(el) {
        el.classList.remove('tumblr-post');
        el.classList.add('tumblr-post-deferred');
        el.querySelectorAll('iframe').forEach(function (iframe) {
            iframe.remove();
        });
        if (!el.querySelector('a')) {
            var href = el.getAttribute('data-href') || '';
            if (href) {
                var link = document.createElement('a');
                link.href = href;
                link.textContent = href;
                el.appendChild(link);
            }
        }
    }

    function deferTumblrInPost(postEl) {
        postEl.querySelectorAll('.tumblr-post').forEach(deferTumblrEmbed);

        postEl.querySelectorAll('iframe.tumblr-embed').forEach(function (iframe) {
            var src = (iframe.getAttribute('src') || '').split('?')[0];
            var placeholder = document.createElement('div');
            placeholder.className = 'tumblr-post-deferred';
            if (src) {
                placeholder.setAttribute('data-href', src);
                var link = document.createElement('a');
                link.href = src;
                link.textContent = src;
                placeholder.appendChild(link);
            }
            iframe.parentNode.replaceChild(placeholder, iframe);
        });
    }

    function activateTumblrEmbed(el) {
        el.classList.remove('tumblr-post-deferred');
        el.classList.add('tumblr-post');
    }

    function reloadTumblrEmbeds() {
        var script = document.createElement('script');
        script.src = 'https://assets.tumblr.com/post.js';
        script.async = true;
        document.body.appendChild(script);
    }

    function postTitle(el, h4, h5) {
        if (h5) {
            return h5.textContent.trim();
        }

        var clone = el.cloneNode(true);
        var heading = clone.querySelector('h4');
        if (heading) {
            heading.remove();
        }
        clone.querySelectorAll('.tumblr-post, .tumblr-post-deferred, script, iframe, img, video, .blog-post-images, .blog-post-video').forEach(function (node) {
            node.remove();
        });
        var extra = clone.textContent.replace(/\s+/g, ' ').trim();
        if (extra && extra.length <= 90 && extra.toLowerCase().indexOf('http') !== 0) {
            return extra;
        }

        var tumblrLink = el.querySelector('.tumblr-post a[href*="tumblr.com"], .tumblr-post-deferred a[href*="tumblr.com"]');
        var href = tumblrLink && tumblrLink.getAttribute('href');
        if (href) {
            var slug = href.replace(/\/$/, '').split('/').pop();
            if (slug && slug !== 'v2' && !/^\d+$/.test(slug) && slug.indexOf('http') !== 0) {
                return slug.replace(/-/g, ' ');
            }
        }

        return h4 ? h4.textContent.trim() : 'Untitled';
    }

    function collectPosts() {
        var seenIds = {};
        var postEls = postsEl.querySelectorAll(':scope > .blog-post');
        if (!postEls.length) {
            postEls = postsEl.querySelectorAll(':scope > .col-lg-6, :scope > .col-md-6');
        }

        posts = Array.prototype.map.call(postEls, function (el) {
            el.classList.add('blog-post');

            var h4 = el.querySelector('h4');
            var h5 = el.querySelector('h5');
            var parsed = parsePostDate(h4 ? h4.textContent : '');
            var id = parsed ? 'blog-' + parsed.iso : '';

            if (id) {
                if (seenIds[id]) {
                    seenIds[id] += 1;
                    id += '-' + seenIds[id];
                } else {
                    seenIds[id] = 1;
                }
                el.id = id;
            }

            el.querySelectorAll('img').forEach(function (img) {
                img.setAttribute('loading', 'lazy');
                img.setAttribute('decoding', 'async');
            });

            enableLiteYouTube(el);
            var title = postTitle(el, h4, h5);
            var searchText = el.textContent.toLowerCase();
            deferTumblrInPost(el);

            return {
                el: el,
                id: id,
                date: parsed,
                monthKey: parsed ? parsed.monthKey : '',
                monthLabel: parsed ? parsed.monthLabel : 'Undated',
                title: title,
                searchText: searchText
            };
        });

        var monthMap = {};
        months = [];
        posts.forEach(function (post) {
            if (!post.monthKey) {
                return;
            }
            if (!monthMap[post.monthKey]) {
                monthMap[post.monthKey] = {
                    key: post.monthKey,
                    label: post.monthLabel,
                    count: 0
                };
                months.push(monthMap[post.monthKey]);
            }
            monthMap[post.monthKey].count += 1;
        });
    }

    function monthFromHash() {
        var hash = window.location.hash.replace(/^#/, '');
        if (hash.indexOf('blog-') !== 0) {
            return null;
        }

        var monthMatch = hash.match(/^blog-(\d{4}-\d{2})(?:-\d{2})?/);
        return monthMatch ? monthMatch[1] : null;
    }

    function postIdFromHash() {
        var hash = window.location.hash.replace(/^#/, '');
        if (/^blog-\d{4}-\d{2}-\d{2}/.test(hash)) {
            return hash;
        }
        return '';
    }

    function setHash(id) {
        if (!id || window.location.hash.replace(/^#/, '') === id) {
            return;
        }
        if (history.replaceState) {
            history.replaceState(null, '', '#' + id);
        }
    }

    function visiblePosts() {
        if (searchQuery) {
            return posts.filter(function (post) {
                return post.searchText.indexOf(searchQuery) !== -1;
            });
        }

        return posts.filter(function (post) {
            return post.monthKey === activeMonth;
        });
    }

    function statusText() {
        var shown = visiblePosts();
        if (searchQuery) {
            return shown.length + ' post' + (shown.length === 1 ? '' : 's') +
                ' matching “' + searchQuery.replace(/</g, '&lt;') + '”';
        }

        var current = months.find(function (month) {
            return month.key === activeMonth;
        });
        return current
            ? 'Showing ' + current.label + ' · ' + current.count + ' post' + (current.count === 1 ? '' : 's')
            : '';
    }

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function postsByDayForMonth(monthKey) {
        var byDay = {};
        posts.forEach(function (post) {
            if (!post.date || post.monthKey !== monthKey) {
                return;
            }
            var day = post.date.day;
            if (!byDay[day]) {
                byDay[day] = [];
            }
            byDay[day].push(post);
        });
        return byDay;
    }

    function calendarHtml(monthKey) {
        if (searchQuery) {
            return '<p class="progress-blog-calendar-note text-muted small mb-0">' +
                'Clear search to browse posts by calendar day.' +
                '</p>';
        }

        if (!monthKey) {
            return '';
        }

        var parts = monthKey.split('-');
        var year = parseInt(parts[0], 10);
        var monthIndex = parseInt(parts[1], 10) - 1;
        if (!year || monthIndex < 0 || monthIndex > 11) {
            return '';
        }

        var monthLabel = MONTH_NAMES[monthIndex] + ' ' + year;
        var firstWeekday = new Date(year, monthIndex, 1).getDay();
        var daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
        var byDay = postsByDayForMonth(monthKey);
        var weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        var cells = [];
        var i;

        for (i = 0; i < firstWeekday; i += 1) {
            cells.push('<span class="progress-blog-cal-day is-empty" aria-hidden="true"></span>');
        }

        for (i = 1; i <= daysInMonth; i += 1) {
            var dayPosts = byDay[i];
            if (dayPosts && dayPosts.length) {
                var post = dayPosts[0];
                var label = MONTH_NAMES[monthIndex] + ' ' + i + ', ' + year + ': ' + post.title;
                if (dayPosts.length > 1) {
                    label += ' (+' + (dayPosts.length - 1) + ' more)';
                }
                cells.push(
                    '<button type="button" class="progress-blog-cal-day has-post"' +
                    ' data-post-id="' + escapeHtml(post.id) + '"' +
                    ' aria-label="' + escapeHtml(label) + '">' +
                    '<span class="progress-blog-cal-num">' + i + '</span>' +
                    '<span class="progress-blog-cal-dot" aria-hidden="true"></span>' +
                    '</button>'
                );
            } else {
                cells.push(
                    '<span class="progress-blog-cal-day">' +
                    '<span class="progress-blog-cal-num">' + i + '</span>' +
                    '</span>'
                );
            }
        }

        while (cells.length % 7 !== 0) {
            cells.push('<span class="progress-blog-cal-day is-empty" aria-hidden="true"></span>');
        }

        return '<div class="progress-blog-calendar" role="group" aria-label="' +
            escapeHtml(monthLabel) + ' post calendar">' +
            '<p class="progress-blog-calendar-title mb-0">' + escapeHtml(monthLabel) + '</p>' +
            '<div class="progress-blog-calendar-weekdays" aria-hidden="true">' +
                weekdayLabels.map(function (day) {
                    return '<span>' + day + '</span>';
                }).join('') +
            '</div>' +
            '<div class="progress-blog-calendar-grid">' + cells.join('') + '</div>' +
            '</div>';
    }

    function updateControls() {
        controlsEl.querySelectorAll('[data-month]').forEach(function (button) {
            var pressed = !searchQuery && button.getAttribute('data-month') === activeMonth;
            button.classList.toggle('is-active', pressed);
            button.setAttribute('aria-pressed', pressed);
        });

        var jump = controlsEl.querySelector('.progress-blog-jump');
        if (jump) {
            jump.innerHTML = '<option value="">Jump to a post</option>' +
                visiblePosts().map(function (post) {
                    return '<option value="' + post.id + '">' + escapeHtml(post.title) + '</option>';
                }).join('');
        }

        var status = controlsEl.querySelector('.progress-blog-status');
        if (status) {
            status.innerHTML = statusText();
        }

        var calendarWrap = controlsEl.querySelector('.progress-blog-calendar-wrap');
        if (calendarWrap) {
            calendarWrap.innerHTML = calendarHtml(activeMonth);
        }
    }

    function renderControls() {
        var monthButtons = months.map(function (month) {
            var pressed = !searchQuery && month.key === activeMonth;
            return '<button type="button" class="progress-blog-month' + (pressed ? ' is-active' : '') + '"' +
                ' data-month="' + month.key + '"' +
                ' aria-pressed="' + pressed + '">' +
                month.label + ' <span class="progress-blog-count">' + month.count + '</span>' +
                '</button>';
        }).join('');

        controlsEl.innerHTML =
            '<div class="progress-blog-months" role="group" aria-label="Browse posts by month">' +
                monthButtons +
            '</div>' +
            '<div class="progress-blog-browse">' +
                '<div class="progress-blog-calendar-wrap"></div>' +
                '<div class="progress-blog-tools-panel">' +
                    '<div class="progress-blog-tools">' +
                        '<label class="progress-blog-search-label">' +
                            '<span class="sr-only">Search posts</span>' +
                            '<input type="search" class="form-control form-control-sm progress-blog-search"' +
                            ' placeholder="Search posts">' +
                        '</label>' +
                        '<label class="progress-blog-jump-label">' +
                            '<span class="sr-only">Jump to a post</span>' +
                            '<select class="form-control form-control-sm progress-blog-jump">' +
                                '<option value="">Jump to a post</option>' +
                            '</select>' +
                        '</label>' +
                    '</div>' +
                    '<p class="progress-blog-status text-muted small mb-0"></p>' +
                '</div>' +
            '</div>';

        updateControls();
    }

    function applyVisibility() {
        var shown = visiblePosts();
        var shownSet = {};
        shown.forEach(function (post) {
            shownSet[post.id] = true;
        });

        var needTumblr = false;
        posts.forEach(function (post) {
            var isVisible = !!shownSet[post.id];
            post.el.classList.toggle('is-visible', isVisible);
            post.el.hidden = !isVisible;

            if (isVisible) {
                post.el.querySelectorAll('.tumblr-post-deferred').forEach(function (el) {
                    activateTumblrEmbed(el);
                    needTumblr = true;
                });
            } else {
                deferTumblrInPost(post.el);
                post.el.querySelectorAll('video').forEach(function (video) {
                    video.pause();
                });
            }
        });

        if (needTumblr) {
            reloadTumblrEmbeds();
        }

        postsEl.classList.add('is-ready');
        if (!controlsEl.dataset.ready) {
            renderControls();
            controlsEl.dataset.ready = 'true';
        } else {
            updateControls();
        }
    }

    function showMonth(monthKey, options) {
        options = options || {};
        searchQuery = '';
        activeMonth = monthKey;
        stopPlayingVideos();
        applyVisibility();

        var searchInput = controlsEl.querySelector('.progress-blog-search');
        if (searchInput) {
            searchInput.value = '';
        }

        if (options.scroll !== false) {
            var target = document.getElementById(options.postId || 'progressblog');
            if (target) {
                target.scrollIntoView({ behavior: options.smooth === false ? 'auto' : 'smooth', block: 'start' });
            }
        }

        if (options.updateHash !== false) {
            setHash(options.postId || ('blog-' + monthKey));
        }
    }

    function showSearch(query) {
        searchQuery = query.trim().toLowerCase();
        stopPlayingVideos();
        applyVisibility();
    }

    function jumpToPost(id) {
        if (!id) {
            return;
        }
        var post = posts.find(function (item) {
            return item.id === id;
        });
        if (!post) {
            return;
        }
        if (searchQuery) {
            var el = document.getElementById(id);
            if (el) {
                el.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            setHash(id);
            return;
        }
        showMonth(post.monthKey, { postId: id });
    }

    function bindControls() {
        controlsEl.addEventListener('click', function (event) {
            var dayButton = event.target.closest('[data-post-id]');
            if (dayButton && controlsEl.contains(dayButton)) {
                jumpToPost(dayButton.getAttribute('data-post-id'));
                return;
            }

            var button = event.target.closest('[data-month]');
            if (!button) {
                return;
            }
            showMonth(button.getAttribute('data-month'));
        });

        controlsEl.addEventListener('input', function (event) {
            if (!event.target.classList.contains('progress-blog-search')) {
                return;
            }
            var value = event.target.value;
            if (!value.trim()) {
                showMonth(activeMonth, { scroll: false });
                return;
            }
            showSearch(value);
        });

        controlsEl.addEventListener('change', function (event) {
            if (!event.target.classList.contains('progress-blog-jump')) {
                return;
            }
            jumpToPost(event.target.value);
            event.target.value = '';
        });
    }

    function applyHash(options) {
        options = options || {};
        var postId = postIdFromHash();
        var monthKey = monthFromHash();

        if (postId && document.getElementById(postId)) {
            var post = posts.find(function (item) {
                return item.id === postId;
            });
            if (post) {
                showMonth(post.monthKey, {
                    postId: postId,
                    scroll: options.scroll !== false,
                    smooth: options.smooth
                });
                return;
            }
        }

        if (monthKey && months.some(function (month) {
            return month.key === monthKey;
        })) {
            showMonth(monthKey, { scroll: options.scroll !== false, smooth: options.smooth });
            return;
        }

        var currentHash = window.location.hash.replace(/^#/, '');
        var preserveHash = currentHash && currentHash.indexOf('blog-') !== 0;
        showMonth(months.length ? months[0].key : '', {
            scroll: false,
            updateHash: !preserveHash
        });

        if (preserveHash) {
            var section = document.getElementById(currentHash);
            if (section) {
                section.scrollIntoView({
                    behavior: options.smooth === false ? 'auto' : 'smooth',
                    block: 'start'
                });
            }
        }
    }

    function init() {
        postsEl = document.getElementById('progressblog-posts');
        controlsEl = document.getElementById('progress-blog-controls');
        if (!postsEl || !controlsEl) {
            return;
        }

        collectPosts();
        if (!posts.length) {
            return;
        }

        bindControls();
        applyHash({ scroll: !!monthFromHash() || !!postIdFromHash(), smooth: false });

        window.addEventListener('hashchange', function () {
            if (window.location.hash.indexOf('#blog-') === 0) {
                applyHash({ scroll: true });
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
