// ==UserScript==
// @name         Bear Notes to ChatGPT
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Auto-paste Bear Notes, get ChatGPT response, and close tab
// @author       Generated Script
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const PORT = 8765;
    const SERVER_URL = `http://localhost:${PORT}/content`;
    const RESPONSE_URL = `http://localhost:${PORT}/response`;

    // Show status notifications
    const showStatus = (() => {
        const el = document.createElement('div');
        Object.assign(el.style, {
            position: 'fixed', top: '10px', left: '50%', transform: 'translateX(-50%)',
            zIndex: '10000', padding: '10px 15px', background: '#10a37f',
            borderRadius: '8px', boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
            color: 'white', fontFamily: 'Arial', fontSize: '14px', fontWeight: 'bold'
        });
        document.body.appendChild(el);

        return (msg, isError) => {
            el.textContent = msg;
            el.style.background = isError ? '#e34234' : '#10a37f';
        };
    })();

    // Wait for ChatGPT UI to load
    const waitForChatGPT = () => new Promise(resolve => {
        const checkExistence = setInterval(() => {
            if (document.querySelector('textarea[placeholder^="Send a message"]') ||
                document.querySelector('div[contenteditable="true"]')) {
                clearInterval(checkExistence);
                resolve();
            }
        }, 500);
    });

    // Fetch content from local server
    const fetchContent = () => new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: 'GET',
            url: SERVER_URL,
            onload: res => {
                if (res.status === 200) {
                    try {
                        resolve(JSON.parse(res.responseText).content);
                    } catch (e) {
                        reject('Error parsing response');
                    }
                } else {
                    reject(`Server error: ${res.status}`);
                }
            },
            onerror: () => reject('Connection error')
        });
    });

    // Fill and submit content to ChatGPT
    const submitToChat = content => {
        // Find input field
        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full'
        ];

        const input = selectors.map(s => document.querySelector(s)).find(el => el);
        if (!input) throw new Error('ChatGPT input not found');

        // Fill input
        input.focus();
        if (input.tagName === 'TEXTAREA') {
            input.value = content;
            // Trigger input event to enable the send button
            input.dispatchEvent(new Event('input', { bubbles: true }));

            // Find and click the send button if it exists
            setTimeout(() => {
                // Look for the send button
                const sendButton = findSendButton();
                if (sendButton) {
                    sendButton.click();
                } else {
                    // If no button found, try enter key as fallback
                    input.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                    }));
                }
            }, 500);
        } else {
            input.innerText = content;
            // Trigger input event to enable the send button
            input.dispatchEvent(new Event('input', { bubbles: true }));

            // Find and click the send button if it exists
            setTimeout(() => {
                // Look for the send button
                const sendButton = findSendButton();
                if (sendButton) {
                    sendButton.click();
                } else {
                    // If no button found, try enter key as fallback
                    input.dispatchEvent(new KeyboardEvent('keydown', {
                        key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                    }));
                }
            }, 500);
        }

        return input;
    };

    // Helper function to find the send button
    const findSendButton = () => {
        // Try various selectors that might match the send button
        const buttonSelectors = [
            'button[aria-label="Send message"]',
            'button[data-testid="send-button"]',
            'button.absolute.p-1.rounded-md',
            'button svg[data-testid="send-icon"]',
            'button.absolute.right-2',
            'button.absolute.bottom-[12px]',
            // Look for buttons with an SVG child
            'button:has(svg)',
            // Look for elements near the input
            'div.absolute.bottom-[12px] button',
            // Try to find by position
            'textarea[placeholder^="Send a message"] + button',
            // Try any button within the chat container
            'form button[type="submit"]'
        ];

        // Try each selector
        for (const selector of buttonSelectors) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                // Check if this is likely a send button (heuristic)
                if (el.tagName === 'BUTTON' &&
                    (el.textContent.trim() === '' || // Empty button (likely just an icon)
                     el.textContent.toLowerCase().includes('send') || // Contains "send" text
                     el.getAttribute('aria-label')?.toLowerCase().includes('send'))) {
                    return el;
                }

                // If it's a button with a send icon
                if (el.querySelector('svg')) {
                    return el;
                }
            }
        }

        // If all else fails, try to find the last button in the form
        const form = document.querySelector('form');
        if (form) {
            const buttons = form.querySelectorAll('button');
            if (buttons.length > 0) {
                return buttons[buttons.length - 1];
            }
        }

        return null;
    };

    // Improved: Check if ChatGPT is thinking
    const isThinking = () => {
        return document.querySelector('.result-thinking') !== null ||
               document.querySelector('[role="progressbar"]') !== null ||
               document.querySelector('.animate-spin') !== null ||
               document.querySelector('[data-state="loading"]') !== null;
    };

    // Improved: Check if response is stable (not changing)
    const getResponseText = () => {
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) return '';
        return responses[responses.length - 1].textContent;
    };

    // Improved: Wait for ChatGPT to finish responding
    const waitForResponse = () => new Promise(resolve => {
        // Check if ChatGPT has started responding
        let started = false;
        let lastResponseText = '';
        let stableCount = 0;

        // Maximum wait time (5 minutes)
        const MAX_WAIT_TIME = 300000;
        const startTime = Date.now();

        const checkStart = setInterval(() => {
            // Check if we've exceeded maximum wait time
            if (Date.now() - startTime > MAX_WAIT_TIME) {
                clearInterval(checkStart);
                showStatus('Maximum wait time exceeded, capturing current response');
                setTimeout(resolve, 1000);
                return;
            }

            // Check if response has started
            if (isThinking() || document.querySelectorAll('[data-message-author-role="assistant"]').length > 0) {
                started = true;

                // Get current response text
                const currentResponseText = getResponseText();

                // If the response text has stabilized (not changing for 5 checks)
                if (currentResponseText === lastResponseText) {
                    stableCount++;

                    // If not thinking and response text is stable for 5 seconds (10 checks of 500ms)
                    if (!isThinking() && stableCount >= 10) {
                        clearInterval(checkStart);
                        // Additional delay to ensure everything is complete
                        setTimeout(resolve, 2000);
                    }
                } else {
                    // Response text changed, reset stable count
                    stableCount = 0;
                    lastResponseText = currentResponseText;
                }
            }
        }, 500);

        // Timeout if response hasn't started after 30 seconds
        setTimeout(() => {
            if (!started) {
                clearInterval(checkStart);
                showStatus('Timeout waiting for response to start', true);
                resolve(); // Maybe response was instantaneous or there was an error
            }
        }, 30000);
    });

    // Get ChatGPT's response text
    const getResponse = () => {
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) throw new Error('No ChatGPT response found');
        // Return raw text content to preserve formatting
        return responses[responses.length - 1].textContent;
    };

    // Send response back to the server
    const sendResponseToServer = response => new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: 'POST',
            url: RESPONSE_URL,
            data: JSON.stringify({ response }),
            headers: { 'Content-Type': 'application/json' },
            onload: res => {
                if (res.status === 200) resolve();
                else reject(`Server error: ${res.status}`);
            },
            onerror: () => reject('Connection error')
        });
    });

    // Main automated workflow
    const run = async () => {
        try {
            await waitForChatGPT();

            showStatus('Fetching content from Bear Notes...');
            const content = await fetchContent();

            showStatus('Submitting to ChatGPT...');
            submitToChat(content);

            showStatus('Waiting for ChatGPT to respond...');
            await waitForResponse();

            showStatus('Capturing response...');
            const response = getResponse();

            showStatus('Sending response back to server...');
            await sendResponseToServer(response);

            showStatus('Done! Closing tab...');
            setTimeout(() => window.close(), 2000);
        } catch (err) {
            showStatus(`Error: ${err.message || err}`, true);
            console.error('Bear to ChatGPT error:', err);
        }
    };

    // Start the process
    run();
})();