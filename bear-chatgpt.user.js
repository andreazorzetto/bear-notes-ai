// ==UserScript==
// @name         Bear Notes to ChatGPT
// @namespace    http://tampermonkey.net/
// @version      1.0
// @description  Automatically paste Bear Notes content into ChatGPT and capture responses
// @author       Generated Script
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    // Configuration
    const serverPort = 8765;
    const serverUrl = `http://localhost:${serverPort}/content`;
    const responseUrl = `http://localhost:${serverPort}/response`;

    // Create UI
    const createUI = () => {
        const container = document.createElement('div');
        container.style.position = 'fixed';
        container.style.bottom = '20px';
        container.style.right = '20px';
        container.style.zIndex = '10000';
        container.style.padding = '10px';
        container.style.background = '#10a37f';
        container.style.borderRadius = '8px';
        container.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
        container.style.color = 'white';
        container.style.fontFamily = 'Arial, sans-serif';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '8px';

        const button = document.createElement('button');
        button.textContent = 'Fetch & Paste Bear Notes';
        button.style.padding = '8px 12px';
        button.style.border = 'none';
        button.style.borderRadius = '4px';
        button.style.backgroundColor = '#fff';
        button.style.color = '#10a37f';
        button.style.fontWeight = 'bold';
        button.style.cursor = 'pointer';

        const captureButton = document.createElement('button');
        captureButton.textContent = 'Capture ChatGPT Response';
        captureButton.style.padding = '8px 12px';
        captureButton.style.border = 'none';
        captureButton.style.borderRadius = '4px';
        captureButton.style.backgroundColor = '#fff';
        captureButton.style.color = '#10a37f';
        captureButton.style.fontWeight = 'bold';
        captureButton.style.cursor = 'pointer';
        captureButton.style.display = 'none'; // Initially hidden

        const status = document.createElement('div');
        status.style.marginTop = '4px';
        status.style.fontSize = '12px';
        status.style.display = 'none';

        container.appendChild(button);
        container.appendChild(captureButton);
        container.appendChild(status);
        document.body.appendChild(container);

        return { button, captureButton, status };
    };

    // Fetch content from local server
    const fetchContent = () => {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'GET',
                url: serverUrl,
                onload: (response) => {
                    if (response.status === 200) {
                        try {
                            const data = JSON.parse(response.responseText);
                            resolve(data.content);
                        } catch (error) {
                            reject('Error parsing content');
                        }
                    } else {
                        reject(`Server error: ${response.status}`);
                    }
                },
                onerror: () => reject('Connection error')
            });
        });
    };

    // Find and fill the ChatGPT input
    const fillChatGPTInput = (content) => {
        // Try multiple selectors for the ChatGPT input
        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full',
            'textarea'
        ];

        let inputElement = null;

        for (const selector of selectors) {
            const element = document.querySelector(selector);
            if (element) {
                inputElement = element;
                break;
            }
        }

        if (!inputElement) {
            throw new Error('ChatGPT input not found');
        }

        // Focus the input
        inputElement.focus();

        // Set the value directly if it's a textarea
        if (inputElement.tagName === 'TEXTAREA') {
            inputElement.value = content;

            // Create and dispatch an input event
            const inputEvent = new Event('input', { bubbles: true });
            inputElement.dispatchEvent(inputEvent);
        }
        // Use innerText if it's a contenteditable div
        else if (inputElement.getAttribute('contenteditable') === 'true') {
            inputElement.innerText = content;

            // Create and dispatch an input event
            const inputEvent = new Event('input', { bubbles: true });
            inputElement.dispatchEvent(inputEvent);
        }

        return inputElement;
    };

    // Wait for ChatGPT to fully load
    const waitForChatGPT = () => {
        return new Promise((resolve) => {
            const checkInterval = setInterval(() => {
                // Check for common elements that indicate the ChatGPT interface is loaded
                if (
                    document.querySelector('textarea[placeholder^="Send a message"]') ||
                    document.querySelector('div[contenteditable="true"]') ||
                    document.querySelector('textarea.w-full')
                ) {
                    clearInterval(checkInterval);
                    resolve();
                }
            }, 500);
        });
    };

    // Send response back to the server
    const sendResponseToServer = (responseText) => {
        return new Promise((resolve, reject) => {
            GM_xmlhttpRequest({
                method: 'POST',
                url: responseUrl,
                data: JSON.stringify({ response: responseText }),
                headers: {
                    'Content-Type': 'application/json'
                },
                onload: (response) => {
                    if (response.status === 200) {
                        try {
                            const data = JSON.parse(response.responseText);
                            resolve(data);
                        } catch (error) {
                            resolve({ success: true }); // Assume success even if parsing fails
                        }
                    } else {
                        reject(`Server error: ${response.status}`);
                    }
                },
                onerror: () => reject('Connection error')
            });
        });
    };

    // Capture the ChatGPT response
    const captureResponse = () => {
        // Find the latest response from ChatGPT
        const responseElements = document.querySelectorAll('[data-message-author-role="assistant"]');

        if (responseElements.length === 0) {
            throw new Error('No ChatGPT response found');
        }

        // Get the latest response
        const latestResponse = responseElements[responseElements.length - 1];

        // Extract the text content
        return latestResponse.textContent;
    };

    // Check if ChatGPT is still thinking
    const isThinking = () => {
        return document.querySelector('.result-thinking') !== null ||
               document.querySelector('[role="progressbar"]') !== null ||
               document.querySelector('.animate-spin') !== null;
    };

    // Wait for ChatGPT to finish responding
    const waitForResponse = () => {
        return new Promise((resolve) => {
            const checkInterval = setInterval(() => {
                if (!isThinking()) {
                    // Give it a small delay to ensure response is complete
                    setTimeout(() => {
                        clearInterval(checkInterval);
                        resolve();
                    }, 1000);
                }
            }, 500);
        });
    };

    // Main function
    const init = async () => {
        await waitForChatGPT();

        const { button, captureButton, status } = createUI();

        button.addEventListener('click', async () => {
            try {
                status.textContent = 'Fetching content...';
                status.style.display = 'block';

                const content = await fetchContent();
                status.textContent = 'Pasting content...';

                const inputElement = fillChatGPTInput(content);

                // Auto-submit the content by simulating Enter key press
                inputElement.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter',
                    code: 'Enter',
                    keyCode: 13,
                    which: 13,
                    bubbles: true
                }));

                status.textContent = 'Content submitted! Waiting for ChatGPT...';

                // Wait for ChatGPT to finish responding
                await waitForResponse();

                // Show the capture button once ChatGPT has responded
                captureButton.style.display = 'block';
                status.textContent = 'ChatGPT has responded! You can now capture the response.';
            } catch (error) {
                status.textContent = `Error: ${error.message || error}`;
                status.style.color = '#ff4c4c';
                setTimeout(() => {
                    status.style.color = 'white';
                }, 5000);
            }
        });

        captureButton.addEventListener('click', async () => {
            try {
                status.textContent = 'Capturing response...';
                status.style.display = 'block';

                const responseText = captureResponse();
                status.textContent = 'Sending response to server...';

                await sendResponseToServer(responseText);

                status.textContent = 'Response sent to server successfully!';
                setTimeout(() => {
                    // Hide the capture button and status after successful capture
                    captureButton.style.display = 'none';
                    status.style.display = 'none';
                }, 3000);
            } catch (error) {
                status.textContent = `Error: ${error.message || error}`;
                status.style.color = '#ff4c4c';
                setTimeout(() => {
                    status.style.color = 'white';
                }, 5000);
            }
        });
    };

    init();
})();