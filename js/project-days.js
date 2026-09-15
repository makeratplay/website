(function () {
    function daysSince(startDateStr) {
        var start = new Date(startDateStr + 'T00:00:00');
        var today = new Date();
        today.setHours(0, 0, 0, 0);
        return Math.max(0, Math.floor((today - start) / 86400000));
    }

    document.querySelectorAll('[data-project-days]').forEach(function (el) {
        var days = daysSince(el.getAttribute('data-project-days'));
        el.textContent = days;

        var label = el.parentElement && el.parentElement.querySelector('.progress-days-label');
        if (label) {
            label.textContent = days === 1 ? 'day' : 'days';
        }
    });

    var timeline = document.querySelector('details.progress-timeline-wrap');
    function openTimelineIfTargeted() {
        if (timeline && window.location.hash === '#progress') {
            timeline.open = true;
        }
    }
    openTimelineIfTargeted();
    window.addEventListener('hashchange', openTimelineIfTargeted);
})();
