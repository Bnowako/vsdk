// Function to get the entire page HTML
function getPageHTML() {
    return document.documentElement.outerHTML;
}

// Debounce function to limit how frequently we send updates
function debounce(fn, delay) {
    let timeoutId;
    return function (...args) {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn(...args), delay);
    };
}

const debouncedSendContent = debounce(() => {
    // You can send this message to your background or directly to your server if needed
    chrome.runtime.sendMessage({
        command: "sendPageContent",
        content: getPageHTML()
    });
}, 500);

// Set up a MutationObserver to watch for changes on the page
const observer = new MutationObserver(() => {
    debouncedSendContent();
});
observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true
});
