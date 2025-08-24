/**
 * Iframe Monitor
 * Detects when iframes are added to the page and monitors their size changes.
 * Manages loading spinners for blog posts with Tumblr embeds.
 */

(function () {
    'use strict';

    // Store watched iframes to avoid duplicate observers
    const watchedIframes = new WeakSet();

    // ResizeObserver to watch for iframe size changes
    const resizeObserver = new ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
            const iframe = entry.target;
            const newHeight = entry.contentRect.height;
            const newWidth = entry.contentRect.width;

            console.log('Iframe size changed:', {
                src: iframe.src || 'No src',
                id: iframe.id || 'No id',
                height: newHeight,
                width: newWidth
            });

            // Check if height is greater than 1000px
            if (newHeight > 500) {
                // Find the parent blog-post container
                const blogPost = iframe.closest('.blog-post');
                if (blogPost) {
                    // Find the loading message within this blog post
                    const loadingMessage = blogPost.querySelector('.loading-message');
                    if (loadingMessage) {
                        loadingMessage.style.display = 'none';
                        console.log('Loading message hidden for iframe:', iframe.src || 'No src');
                    }
                }
            }
        });
    });

    // Function to start watching an iframe for size changes
    function watchIframeSize(iframe) {
        if (!watchedIframes.has(iframe)) {
            resizeObserver.observe(iframe);
            watchedIframes.add(iframe);
            console.log('Started watching iframe:', {
                src: iframe.src || 'No src',
                id: iframe.id || 'No id'
            });
        }
    }

    // Create a MutationObserver to watch for iframe additions
    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            if (mutation.type === 'childList') {
                mutation.addedNodes.forEach(function (node) {
                    // Check if the added node is an iframe
                    if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'IFRAME') {
                        console.log('New iframe detected:', {
                            src: node.src || 'No src',
                            id: node.id || 'No id'
                        });
                        // Start watching this iframe for size changes
                        watchIframeSize(node);
                    }

                    // Also check if any child elements of the added node are iframes
                    if (node.nodeType === Node.ELEMENT_NODE && node.querySelectorAll) {
                        const iframes = node.querySelectorAll('iframe');
                        iframes.forEach(function (iframe) {
                            console.log('New iframe detected (nested):', {
                                src: iframe.src || 'No src',
                                id: iframe.id || 'No id'
                            });
                            // Start watching this iframe for size changes
                            watchIframeSize(iframe);
                        });
                    }
                });
            }
        });
    });

    // Function to add loading messages to blog posts
    function addLoadingMessages() {
        const blogPosts = document.querySelectorAll('.blog-post');
        blogPosts.forEach(function (blogPost) {
            const h4 = blogPost.querySelector('h4');
            if (h4 && !blogPost.querySelector('.loading-message')) {
                // Create loading message element
                const loadingMessage = document.createElement('div');
                loadingMessage.className = 'loading-message';
                loadingMessage.style.cssText = 'text-align: center; color: #666; font-style: italic; margin: 10px 0;';

                // Create spinner element
                const spinner = document.createElement('div');
                spinner.className = 'loading-spinner';

                // Create text node
                const textNode = document.createTextNode('Loading blog post...');

                // Append spinner and text to loading message
                loadingMessage.appendChild(spinner);
                loadingMessage.appendChild(textNode);

                // Insert loading message after the h4
                h4.insertAdjacentElement('afterend', loadingMessage);
            }
        });
    }

    // Function to watch existing iframes
    function watchExistingIframes() {
        const existingIframes = document.querySelectorAll('iframe');
        if (existingIframes.length > 0) {
            console.log('Found', existingIframes.length, 'existing iframes on page load');
            existingIframes.forEach(function (iframe) {
                console.log('Existing iframe:', {
                    src: iframe.src || 'No src',
                    id: iframe.id || 'No id'
                });
                // Start watching existing iframes for size changes
                watchIframeSize(iframe);
            });
        }
    }

    // Initialize the iframe monitor
    function initIframeMonitor() {
        // Start observing changes to the document body and its descendants
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Add loading messages to blog posts
        addLoadingMessages();

        // Watch existing iframes
        watchExistingIframes();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initIframeMonitor);
    } else {
        initIframeMonitor();
    }

})();
