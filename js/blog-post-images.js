/**
 * Blog Post Images
 * Opens full-size images from blog posts in the on-page imgViewer modal.
 */

(function () {
    'use strict';

    var state = {
        images: [],
        index: 0
    };

    var viewer;
    var viewerImg;
    var prevBtn;
    var nextBtn;

    function ensureViewer() {
        viewer = document.getElementById('imgViewer');
        if (!viewer) {
            return null;
        }

        if (viewer.dataset.blogViewerInit === 'true') {
            return viewer;
        }

        viewer.dataset.blogViewerInit = 'true';
        viewer.removeAttribute('onclick');
        viewer.innerHTML = '';

        prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.className = 'img-viewer-nav img-viewer-prev';
        prevBtn.setAttribute('aria-label', 'Previous image');
        prevBtn.innerHTML = '&#10094;';

        nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.className = 'img-viewer-nav img-viewer-next';
        nextBtn.setAttribute('aria-label', 'Next image');
        nextBtn.innerHTML = '&#10095;';

        viewerImg = document.createElement('img');
        viewerImg.className = 'modal-content';
        viewerImg.alt = '';

        viewer.appendChild(prevBtn);
        viewer.appendChild(viewerImg);
        viewer.appendChild(nextBtn);

        prevBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            showImageAt(state.index - 1);
        });

        nextBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            showImageAt(state.index + 1);
        });

        viewerImg.addEventListener('click', function (e) {
            e.stopPropagation();
        });

        viewer.addEventListener('click', function () {
            viewer.style.display = 'none';
        });

        return viewer;
    }

    function isViewerOpen() {
        return viewer && viewer.style.display === 'block';
    }

    function getPostImages(anchor) {
        var body = anchor.closest('.blog-post-body');
        if (!body) {
            return [];
        }

        var images = [];
        body.querySelectorAll('.blog-post-images a img, a.blog-post-image-contain img').forEach(function (img) {
            images.push(img);
        });
        return images;
    }

    function updateNavButtons() {
        var hasMultiple = state.images.length > 1;
        prevBtn.style.display = hasMultiple ? '' : 'none';
        nextBtn.style.display = hasMultiple ? '' : 'none';
        prevBtn.disabled = state.index <= 0;
        nextBtn.disabled = state.index >= state.images.length - 1;
    }

    function showImageAt(index) {
        if (!viewer || index < 0 || index >= state.images.length) {
            return;
        }

        state.index = index;
        var img = state.images[index];
        var anchor = img.closest('a');

        viewerImg.src = anchor && anchor.href ? anchor.href : img.src;
        viewerImg.alt = img.alt || '';
        updateNavButtons();
    }

    function openImageViewer(img) {
        if (!ensureViewer()) {
            return;
        }

        var anchor = img.closest('a');
        if (!anchor) {
            return;
        }

        state.images = getPostImages(anchor);
        state.index = Math.max(0, state.images.indexOf(img));

        showImageAt(state.index);
        viewer.style.display = 'block';
    }

    function initBlogPostImages() {
        var selectors = '.blog-post-body .blog-post-images a, .blog-post-body a.blog-post-image-contain';

        document.querySelectorAll(selectors).forEach(function (anchor) {
            anchor.addEventListener('click', function (e) {
                var img = anchor.querySelector('img');
                if (!img) {
                    return;
                }

                e.preventDefault();
                openImageViewer(img);
            });
        });

        document.addEventListener('keydown', function (e) {
            if (!isViewerOpen()) {
                return;
            }

            if (e.key === 'Escape') {
                viewer.style.display = 'none';
            } else if (e.key === 'ArrowLeft') {
                e.preventDefault();
                showImageAt(state.index - 1);
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                showImageAt(state.index + 1);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBlogPostImages);
    } else {
        initBlogPostImages();
    }
})();
