// ==UserScript==
// @name         Bear Notes to ChatGPT with Improved Chunking
// @namespace    http://tampermonkey.net/
// @version      2.0
// @description  Auto-paste Bear Notes with smart chunking for long content, get ChatGPT response, and close tab
// @author       Generated Script (Enhanced)
// @match        https://chatgpt.com/*
// @grant        GM_xmlhttpRequest
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    const PORT = 8765;
    const SERVER_URL = `http://localhost:${PORT}/content`;
    const RESPONSE_URL = `http://localhost:${PORT}/response`;

    // Config for chunking
    const CHUNK_SIZE_INITIAL = 10000; // Start with this chunk size
    const CHUNK_SIZE_MIN = 1000;      // Minimum chunk size to try
    const CHUNK_REDUCTION_FACTOR = 0.7; // How much to reduce chunk size when hitting limits

    // Improved chunking strategy templates
    const INITIAL_MESSAGE_TEMPLATE =
        "I'm sending a document in {totalChunks} chunks. Do not respond or process until I say 'ALL PARTS SENT'. " +
        "After all parts are received, please {question}";

    const CHUNK_MESSAGE_TEMPLATE =
        "Chunk {currentChunk}/{totalChunks}:\n\n" +
        "{chunkContent}\n\n" +
        "--- End of Chunk {currentChunk}/{totalChunks} ---";

    const FINAL_MESSAGE_TEMPLATE =
        "ALL PARTS SENT.\n" +
        "To confirm, I've sent {totalChunks} chunks of content.\n" +
        "Please now {question}";

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
        const interval = setInterval(() => {
            if (document.querySelector('textarea[placeholder^="Send a message"]') ||
                document.querySelector('div[contenteditable="true"]')) {
                clearInterval(interval);
                resolve();
            }
        }, 500);
    });

    // Get content from local server
    const fetchContent = () => new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: 'GET',
            url: SERVER_URL,
            onload: (response) => {
                if (response.status === 200) {
                    try {
                        const data = JSON.parse(response.responseText);
                        resolve({
                            content: data.content,
                            question: data.question || "analyze the complete document and provide a comprehensive response"
                        });
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

    // Find the send button using multiple strategies
    const findSendButton = () => {
        const buttonSelectors = [
            'button[aria-label="Send message"]',
            'button[data-testid="send-button"]',
            'button.absolute.p-1.rounded-md',
            'button svg[data-testid="send-icon"]',
            'button.absolute.right-2',
            'button:has(svg)',
            'form button[type="submit"]'
        ];

        // Try each selector
        for (const selector of buttonSelectors) {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                if (el.tagName === 'BUTTON' &&
                    (el.textContent.trim() === '' ||
                     el.textContent.toLowerCase().includes('send') ||
                     el.getAttribute('aria-label')?.toLowerCase().includes('send'))) {
                    return el;
                }

                if (el.querySelector('svg')) {
                    return el;
                }
            }
        }

        // Try the last button in the form as fallback
        const form = document.querySelector('form');
        if (form) {
            const buttons = form.querySelectorAll('button');
            if (buttons.length > 0) {
                return buttons[buttons.length - 1];
            }
        }

        return null;
    };

    // Check if message is too long to submit
    const isMessageTooLong = () => {
        // Look for any error message about length
        const errorTexts = [
            'Message is too long',
            'too long',
            'exceeds',
            'limit',
            'character limit'
        ];

        const errorElements = document.querySelectorAll('.text-red-500, .text-red-600, [role="alert"], .text-error, .error-message');
        for (const el of errorElements) {
            const text = el.textContent.toLowerCase();
            if (errorTexts.some(err => text.includes(err))) {
                return true;
            }
        }

        // Check if the send button is disabled despite text in the input
        const input = findChatInput();
        const sendButton = findSendButton();
        if (input && sendButton &&
            ((input.tagName === 'TEXTAREA' && input.value.trim().length > 0) ||
             (input.tagName !== 'TEXTAREA' && input.innerText.trim().length > 0)) &&
            (sendButton.disabled || sendButton.getAttribute('aria-disabled') === 'true')) {
            return true;
        }

        return false;
    };

    // Find the chat input field
    const findChatInput = () => {
        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full'
        ];

        return selectors.map(s => document.querySelector(s)).find(el => el);
    };

    // Fill the chat input with content
    const fillChatInput = (content) => {
        const input = findChatInput();
        if (!input) throw new Error('ChatGPT input not found');

        input.focus();
        if (input.tagName === 'TEXTAREA') {
            input.value = content;
        } else {
            input.innerText = content;
        }

        // Trigger input event to enable the send button
        input.dispatchEvent(new Event('input', { bubbles: true }));

        return input;
    };

    // Clear the chat input
    const clearChatInput = () => {
        const input = findChatInput();
        if (input) {
            input.focus();
            if (input.tagName === 'TEXTAREA') {
                input.value = '';
            } else {
                input.innerText = '';
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
        }
    };

    // Try to submit content to ChatGPT
    const submitMessage = async (message) => {
        return new Promise((resolve, reject) => {
            try {
                // Fill the input with the message
                fillChatInput(message);

                // Check for length errors after a brief delay
                setTimeout(() => {
                    if (isMessageTooLong()) {
                        // Message is too long, resolve with false
                        clearChatInput();
                        resolve(false);
                    } else {
                        // Try to click the send button
                        const sendButton = findSendButton();
                        if (sendButton) {
                            sendButton.click();
                            resolve(true);
                        } else {
                            // Fallback to Enter key
                            const input = findChatInput();
                            if (input) {
                                input.dispatchEvent(new KeyboardEvent('keydown', {
                                    key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true
                                }));
                                resolve(true);
                            } else {
                                reject('Send button and input not found');
                            }
                        }
                    }
                }, 300);
            } catch (err) {
                reject(err);
            }
        });
    };

    // Estimate how many chunks we'll need based on content length and initial chunk size
    const estimateTotalChunks = (content, chunkSize) => {
        return Math.ceil(content.length / chunkSize);
    };

    // Format message according to templates
    const formatMessage = (type, params) => {
        switch(type) {
            case 'initial':
                return INITIAL_MESSAGE_TEMPLATE
                    .replace('{totalChunks}', params.totalChunks)
                    .replace('{question}', params.question || "analyze the complete document and provide a comprehensive response");
            case 'chunk':
                return CHUNK_MESSAGE_TEMPLATE
                    .replace(/{currentChunk}/g, params.currentChunk)
                    .replace(/{totalChunks}/g, params.totalChunks)
                    .replace('{chunkContent}', params.chunkContent);
            case 'final':
                return FINAL_MESSAGE_TEMPLATE
                    .replace('{totalChunks}', params.totalChunks)
                    .replace('{question}', params.question || "analyze the complete document and provide a comprehensive response");
            default:
                return '';
        }
    };

    // Process content in chunks with improved formatting
    const processContent = async (content, question = "analyze the complete document and provide a comprehensive response") => {
        let remainingContent = content;
        let chunkSize = CHUNK_SIZE_INITIAL;
        let actualChunkNum = 0;
        let estimatedTotalChunks = estimateTotalChunks(content, chunkSize);
        let needsChunking = estimatedTotalChunks > 1;

        // If content fits in one message, send it directly
        if (!needsChunking) {
            showStatus('Content fits in a single message, sending...');
            await submitMessage(content);
            await waitForResponse(); // Add this line
            return await getChatGPTResponse();
        }

        // Send initial message explaining the chunking process
        showStatus('Sending initial chunking message with the question...');
        const initialMessage = formatMessage('initial', { totalChunks: estimatedTotalChunks, question: question });
        await submitMessage(initialMessage);
        await waitForResponse();

        // Process each chunk
        let actualChunks = [];
        while (remainingContent.length > 0) {
            actualChunkNum++;
            const isLastChunk = (remainingContent.length <= chunkSize);

            showStatus(`Processing chunk ${actualChunkNum}/${estimatedTotalChunks}... (${remainingContent.length} chars remaining)`);

            // Extract the next chunk
            let currentChunk = remainingContent.substring(0, chunkSize);

            // Format the chunk message - include ALL PARTS SENT in the last chunk
            let chunkMessage;
            if (isLastChunk) {
                // For the last chunk, include the completion message in the same message
                chunkMessage = formatMessage('chunk', {
                    currentChunk: actualChunkNum,
                    totalChunks: estimatedTotalChunks,
                    chunkContent: currentChunk
                }) + "\n\n" + formatMessage('final', { totalChunks: actualChunkNum, question: question });
            } else {
                chunkMessage = formatMessage('chunk', {
                    currentChunk: actualChunkNum,
                    totalChunks: estimatedTotalChunks,
                    chunkContent: currentChunk
                });
            }

            // Try to submit the chunk, reduce size if too large
            let success = false;
            while (!success && chunkSize >= CHUNK_SIZE_MIN) {
                try {
                    success = await submitMessage(chunkMessage);

                    if (!success) {
                        // Reduce chunk size and try again
                        chunkSize = Math.max(Math.floor(chunkSize * CHUNK_REDUCTION_FACTOR), CHUNK_SIZE_MIN);
                        showStatus(`Chunk too large, reducing to ${chunkSize} chars...`);

                        // We need to recalculate the total chunks estimate
                        estimatedTotalChunks = Math.max(
                            estimatedTotalChunks,
                            actualChunkNum + Math.ceil(remainingContent.length / chunkSize)
                        );

                        // Recalculate the current chunk with new size
                        currentChunk = remainingContent.substring(0, chunkSize);
                        isLastChunk = (remainingContent.length <= chunkSize);

                        // Reformat with updated values - handle last chunk case
                        let updatedChunkMessage;
                        if (isLastChunk) {
                            updatedChunkMessage = formatMessage('chunk', {
                                currentChunk: actualChunkNum,
                                totalChunks: estimatedTotalChunks,
                                chunkContent: currentChunk
                            }) + "\n\n" + formatMessage('final', { totalChunks: actualChunkNum, question: question });
                        } else {
                            updatedChunkMessage = formatMessage('chunk', {
                                currentChunk: actualChunkNum,
                                totalChunks: estimatedTotalChunks,
                                chunkContent: currentChunk
                            });
                        }

                        // Try again with the smaller chunk
                        clearChatInput();
                        success = await submitMessage(updatedChunkMessage);
                    }
                } catch (err) {
                    console.error('Error submitting chunk:', err);
                    throw err;
                }
            }

            if (!success) {
                throw new Error(`Failed to submit chunk even at minimum size ${CHUNK_SIZE_MIN}`);
            }

            // Wait for ChatGPT to process the chunk
            await waitForResponse();

            // Store the processed chunk for tracking
            actualChunks.push(currentChunk);

            // Remove the processed chunk from remaining content
            remainingContent = remainingContent.substring(chunkSize);

            // If there's more content, wait briefly before continuing
            if (remainingContent.length > 0) {
                showStatus('Preparing next chunk...');
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }

        // For the last chunk we already sent the "ALL PARTS SENT" message
        // So we just need to return the final response
        return await getChatGPTResponse();
    };

    // Check if ChatGPT is still generating a response
    const isThinking = () => {
        return document.querySelector('.result-thinking') !== null ||
               document.querySelector('[role="progressbar"]') !== null ||
               document.querySelector('.animate-spin') !== null ||
               document.querySelector('[data-state="loading"]') !== null;
    };

    // Get current response text from ChatGPT
    const getResponseText = () => {
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) return '';
        return responses[responses.length - 1].textContent;
    };

    // Wait for ChatGPT to finish responding
    const waitForResponse = () => new Promise(resolve => {
        let started = false;
        let lastResponseText = '';
        let stableCount = 0;
        const MAX_WAIT_TIME = 300000; // 5 minutes
        const startTime = Date.now();

        const checkResponse = setInterval(() => {
            // Check if maximum wait time exceeded
            if (Date.now() - startTime > MAX_WAIT_TIME) {
                clearInterval(checkResponse);
                showStatus('Maximum wait time exceeded, capturing current response');
                setTimeout(resolve, 1000);
                return;
            }

            // Check if response has started
            if (isThinking() || document.querySelectorAll('[data-message-author-role="assistant"]').length > 0) {
                started = true;
                const currentResponseText = getResponseText();

                // Check if response has stabilized
                if (currentResponseText === lastResponseText) {
                    stableCount++;
                    if (!isThinking() && stableCount >= 10) {
                        clearInterval(checkResponse);
                        setTimeout(resolve, 2000);
                    }
                } else {
                    stableCount = 0;
                    lastResponseText = currentResponseText;
                }
            }
        }, 500);

        // Timeout if response hasn't started after 30 seconds
        setTimeout(() => {
            if (!started) {
                clearInterval(checkResponse);
                showStatus('Timeout waiting for response', true);
                resolve();
            }
        }, 30000);
    });

    // Get the final response from ChatGPT
    const getChatGPTResponse = () => {
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) throw new Error('No ChatGPT response found');
        return responses[responses.length - 1].textContent;
    };

    // Send response back to the local server
    const sendResponseToServer = response => new Promise((resolve, reject) => {
        GM_xmlhttpRequest({
            method: 'POST',
            url: RESPONSE_URL,
            data: JSON.stringify({ response }),
            headers: { 'Content-Type': 'application/json' },
            onload: (response) => {
                if (response.status === 200) resolve();
                else reject(`Server error: ${response.status}`);
            },
            onerror: () => reject('Connection error')
        });
    });

    // Main workflow
    const run = async () => {
        try {
            await waitForChatGPT();
            showStatus('Fetching content from Bear Notes...');
            const { content, question } = await fetchContent();

            showStatus('Processing content...');
            const response = await processContent(content, question);

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