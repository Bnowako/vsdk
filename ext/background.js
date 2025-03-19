// Relay messages from content script to sidebar
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.command === "sendPageContent") {
    chrome.runtime.sendMessage(message);
  }
});

// Handle sidebar button click
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId });
});
