// ==UserScript==
// @name         Bear Notes to ChatGPT with Enhanced Chunking
// @namespace    http://tampermonkey.net/
// @version      2.1
// @description  Auto-paste Bear Notes with smart chunking for long content, get ChatGPT response, and close tab
// @author       Enhanced Script
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @grant        GM_xmlhttpRequest
// @grant        GM_setValue
// @grant        GM_getValue
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    // Configuration - can be customized
    const CONFIG = {
        PORT: 8765,
        CHUNK_SIZE_INITIAL: 10000,  // Start with this chunk size
        CHUNK_SIZE_MIN: 1000,       // Minimum chunk size to try
        CHUNK_REDUCTION_FACTOR: 0.7, // How much to reduce chunk size when hitting limits
        RETRY_ATTEMPTS: 3,          // Number of retries for network operations
        RETRY_DELAY: 2000,          // Delay between retries in milliseconds
        AUTO_CLOSE_DELAY: 3000,     // Time to wait before closing tab after completion
        DEBUG_MODE: false           // Set to true to enable debug messages
    };

    // URLs for API endpoints
    const SERVER_URL = `http://localhost:${CONFIG.PORT}/content`;
    const RESPONSE_URL = `http://localhost:${CONFIG.PORT}/response`;

    // Improved chunking strategy templates
    const TEMPLATES = {
        INITIAL_MESSAGE:
            "I'm sending a document in {totalChunks} chunks. Do not respond or process until I say 'ALL PARTS SENT'. " +
            "After all parts are received, please {question}",

        CHUNK_MESSAGE:
            "Chunk {currentChunk}/{totalChunks}:\n\n" +
            "{chunkContent}\n\n" +
            "--- End of Chunk {currentChunk}/{totalChunks} ---",

        FINAL_MESSAGE:
            "ALL PARTS SENT.\n" +
            "To confirm, I've sent {totalChunks} chunks of content.\n" +
            "Please now {question}"
    };

    // Utility to log messages conditionally based on debug mode
    const logger = {
        info: (msg) => {
            if (CONFIG.DEBUG_MODE) console.log(`%c[INFO] ${msg}`, 'color: #3498db');
        },
        success: (msg) => {
            if (CONFIG.DEBUG_MODE) console.log(`%c[SUCCESS] ${msg}`, 'color: #2ecc71');
        },
        warn: (msg) => {
            if (CONFIG.DEBUG_MODE) console.log(`%c[WARNING] ${msg}`, 'color: #f39c12');
        },
        error: (msg) => {
            console.error(`%c[ERROR] ${msg}`, 'color: #e74c3c'); // Always show errors
        }
    };

    // Show status notifications
    const showStatus = (() => {
        const el = document.createElement('div');
        Object.assign(el.style, {
            position: 'fixed', top: '10px', left: '50%', transform: 'translateX(-50%)',
            zIndex: '10000', padding: '10px 15px', background: '#10a37f',
            borderRadius: '8px', boxShadow: '0 2px 10px rgba(0,0,0,0.2)',
            color: 'white', fontFamily: 'Arial', fontSize: '14px', fontWeight: 'bold',
            transition: 'background-color 0.3s ease'
        });
        document.body.appendChild(el);

        return (msg, type = 'info') => {
            el.textContent = msg;

            // Set color based on message type
            switch(type) {
                case 'error':
                    el.style.background = '#e34234';
                    break;
                case 'warning':
                    el.style.background = '#f39c12';
                    break;
                case 'success':
                    el.style.background = '#2ecc71';
                    break;
                default:
                    el.style.background = '#10a37f';
            }

            // Log to console as well
            if (type === 'error') logger.error(msg);
            else if (type === 'warning') logger.warn(msg);
            else if (type === 'success') logger.success(msg);
            else logger.info(msg);
        };
    })();

    // Wait for ChatGPT UI to load
    const waitForChatGPT = () => new Promise(resolve => {
        logger.info("Waiting for ChatGPT UI to load...");

        const checkForElements = () => {
            const textArea = document.querySelector('textarea[placeholder^="Send a message"]');
            const contentEditable = document.querySelector('div[contenteditable="true"]');

            if (textArea || contentEditable) {
                logger.success("ChatGPT UI loaded");
                return true;
            }
            return false;
        };

        // Check immediately
        if (checkForElements()) {
            resolve();
            return;
        }

        // Set up observer to watch for UI elements
        const observer = new MutationObserver(() => {
            if (checkForElements()) {
                observer.disconnect();
                resolve();
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Fallback timeout
        setTimeout(() => {
            observer.disconnect();
            if (checkForElements()) {
                resolve();
            } else {
                // Try to resolve anyway after timeout
                logger.warn("Timeout waiting for UI, proceeding anyway");
                resolve();
            }
        }, 10000);
    });

    // Get content from local server with retry
    const fetchContentWithRetry = async () => {
        for (let attempt = 1; attempt <= CONFIG.RETRY_ATTEMPTS; attempt++) {
            try {
                return await fetchContent();
            } catch (error) {
                if (attempt < CONFIG.RETRY_ATTEMPTS) {
                    const delay = CONFIG.RETRY_DELAY * attempt; // Exponential backoff
                    logger.warn(`Fetch attempt ${attempt} failed: ${error}. Retrying in ${delay/1000}s...`);
                    showStatus(`Connection attempt ${attempt} failed. Retrying...`, 'warning');
                    await new Promise(resolve => setTimeout(resolve, delay));
                } else {
                    throw error; // Rethrow after all retries fail
                }
            }
        }
    };

    // Get content from local server
    const fetchContent = () => new Promise((resolve, reject) => {
        showStatus('Connecting to Bear Notes server...');

        GM_xmlhttpRequest({
            method: 'GET',
            url: SERVER_URL,
            timeout: 30000, // 30 second timeout
            onload: (response) => {
                if (response.status === 200) {
                    try {
                        const data = JSON.parse(response.responseText);
                        resolve({
                            content: data.content,
                            question: data.question || "analyze the complete document and provide a comprehensive response"
                        });
                    } catch (error) {
                        reject(`Error parsing content: ${error.message}`);
                    }
                } else {
                    reject(`Server error: ${response.status} - ${response.statusText || 'Unknown error'}`);
                }
            },
            onerror: (error) => reject(`Connection error: ${error.message || 'Failed to connect'}`),
            ontimeout: () => reject('Connection timed out')
        });
    });

    // Find the send button using multiple strategies
    const findSendButton = () => {
        logger.info("Looking for send button...");

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
                    logger.success(`Found send button using selector: ${selector}`);
                    return el;
                }

                if (el.querySelector('svg')) {
                    logger.success(`Found send button with SVG using selector: ${selector}`);
                    return el;
                }
            }
        }

        // Try the last button in the form as fallback
        const form = document.querySelector('form');
        if (form) {
            const buttons = form.querySelectorAll('button');
            if (buttons.length > 0) {
                logger.success("Found send button as last button in form");
                return buttons[buttons.length - 1];
            }
        }

        logger.error("Could not find send button");
        return null;
    };

    // Check if message is too long to submit
    const isMessageTooLong = () => {
        // Look for any error message about length
        const errorTexts = [
            'message is too long',
            'too long',
            'exceeds',
            'limit',
            'character limit'
        ];

        // Check for visible error messages
        const errorElements = document.querySelectorAll('.text-red-500, .text-red-600, [role="alert"], .text-error, .error-message');
        for (const el of errorElements) {
            const text = el.textContent.toLowerCase();
            if (errorTexts.some(err => text.includes(err))) {
                logger.warn(`Detected error message: "${el.textContent}"`);
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
            logger.warn("Send button is disabled despite text in input");
            return true;
        }

        return false;
    };

    // Find the chat input field
    const findChatInput = () => {
        logger.info("Looking for chat input...");

        const selectors = [
            'textarea[placeholder^="Send a message"]',
            'div[contenteditable="true"]',
            'textarea.w-full'
        ];

        const input = selectors.map(s => document.querySelector(s)).find(el => el);

        if (input) {
            logger.success(`Found chat input: ${input.tagName}`);
        } else {
            logger.error("Could not find chat input");
        }

        return input;
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
        logger.info(`Filled chat input with ${content.length} characters`);

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
            logger.info("Cleared chat input");
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
                        logger.warn("Message is too long");
                        clearChatInput();
                        resolve(false);
                    } else {
                        // Try to click the send button
                        const sendButton = findSendButton();
                        if (sendButton) {
                            logger.info("Clicking send button");
                            sendButton.click();
                            resolve(true);
                        } else {
                            // Fallback to Enter key
                            const input = findChatInput();
                            if (input) {
                                logger.info("Using Enter key fallback");
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
                return TEMPLATES.INITIAL_MESSAGE
                    .replace('{totalChunks}', params.totalChunks)
                    .replace('{question}', params.question || "analyze the complete document and provide a comprehensive response");
            case 'chunk':
                return TEMPLATES.CHUNK_MESSAGE
                    .replace(/{currentChunk}/g, params.currentChunk)
                    .replace(/{totalChunks}/g, params.totalChunks)
                    .replace('{chunkContent}', params.chunkContent);
            case 'final':
                return TEMPLATES.FINAL_MESSAGE
                    .replace('{totalChunks}', params.totalChunks)
                    .replace('{question}', params.question || "analyze the complete document and provide a comprehensive response");
            default:
                return '';
        }
    };

    // Process content in chunks with improved formatting
    const processContent = async (content, question = "analyze the complete document and provide a comprehensive response") => {
        let remainingContent = content;
        let chunkSize = CONFIG.CHUNK_SIZE_INITIAL;
        let actualChunkNum = 0;
        let estimatedTotalChunks = estimateTotalChunks(content, chunkSize);
        let needsChunking = estimatedTotalChunks > 1;

        // If content fits in one message, send it directly
        if (!needsChunking) {
            showStatus('Content fits in a single message, sending...', 'info');
            logger.info("Content will be sent as a single message");

            // For short content, combine the question with the content
            const formattedContent = `${question}\n\n${content}`;
            await submitMessage(formattedContent);
            return await getChatGPTResponse();
        }

        // Send initial message explaining the chunking process
        showStatus(`Preparing to send document in ${estimatedTotalChunks} chunks...`, 'info');
        const initialMessage = formatMessage('initial', { totalChunks: estimatedTotalChunks, question: question });

        logger.info(`Sending initial message: "${initialMessage.substring(0, 100)}..."`);
        await submitMessage(initialMessage);
        await waitForResponse();

        // Process each chunk
        let actualChunks = [];
        while (remainingContent.length > 0) {
            actualChunkNum++;
            const isLastChunk = (remainingContent.length <= chunkSize);

            showStatus(`Processing chunk ${actualChunkNum}/${estimatedTotalChunks}... (${remainingContent.length} chars remaining)`, 'info');
            logger.info(`Processing chunk ${actualChunkNum}/${estimatedTotalChunks}, ${remainingContent.length} chars remaining`);

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
                logger.info(`Formatted last chunk (${actualChunkNum}) with completion message`);
            } else {
                chunkMessage = formatMessage('chunk', {
                    currentChunk: actualChunkNum,
                    totalChunks: estimatedTotalChunks,
                    chunkContent: currentChunk
                });
                logger.info(`Formatted chunk ${actualChunkNum}`);
            }

            // Try to submit the chunk, reduce size if too large
            let success = false;
            let sizeReductionAttempts = 0;

            while (!success && chunkSize >= CONFIG.CHUNK_SIZE_MIN) {
                try {
                    logger.info(`Attempting to submit chunk with size ${chunkSize}`);
                    success = await submitMessage(chunkMessage);

                    if (!success) {
                        // Reduce chunk size and try again
                        sizeReductionAttempts++;
                        const previousSize = chunkSize;
                        chunkSize = Math.max(Math.floor(chunkSize * CONFIG.CHUNK_REDUCTION_FACTOR), CONFIG.CHUNK_SIZE_MIN);

                        showStatus(`Chunk too large, reducing size from ${previousSize} to ${chunkSize} chars...`, 'warning');
                        logger.warn(`Chunk too large, reducing from ${previousSize} to ${chunkSize} chars (attempt ${sizeReductionAttempts})`);

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

                        // Update the message to send
                        chunkMessage = updatedChunkMessage;

                        // Try again with the smaller chunk
                        clearChatInput();
                    }
                } catch (err) {
                    logger.error(`Error submitting chunk: ${err.message || err}`);
                    throw err;
                }
            }

            if (!success) {
                showStatus(`Failed to submit chunk even at minimum size ${CONFIG.CHUNK_SIZE_MIN}`, 'error');
                throw new Error(`Failed to submit chunk even at minimum size ${CONFIG.CHUNK_SIZE_MIN}`);
            }

            // Wait for ChatGPT to process the chunk
            showStatus(`Waiting for ChatGPT to process chunk ${actualChunkNum}...`, 'info');
            await waitForResponse();

            // Store the processed chunk for tracking
            actualChunks.push(currentChunk);

            // Remove the processed chunk from remaining content
            remainingContent = remainingContent.substring(chunkSize);

            // If there's more content, wait briefly before continuing
            if (remainingContent.length > 0) {
                showStatus(`Preparing next chunk...`, 'info');
                await new Promise(resolve => setTimeout(resolve, 1000));
            }
        }

        // For the last chunk we already sent the "ALL PARTS SENT" message
        // So we just need to return the final response
        showStatus(`All chunks sent. Getting final response...`, 'success');
        return await getChatGPTResponse();
    };

    // Check if ChatGPT is still generating a response
    const isThinking = () => {
        const thinkingIndicators = [
            '.result-thinking',
            '[role="progressbar"]',
            '.animate-spin',
            '[data-state="loading"]',
            '.text-token-text-secondary' // For new UI versions
        ];

        for (const selector of thinkingIndicators) {
            if (document.querySelector(selector)) {
                return true;
            }
        }

        return false;
    };

    // Get current response text from ChatGPT
    const getResponseText = () => {
        const selectors = [
            '[data-message-author-role="assistant"]',
            '.markdown' // For newer UI versions
        ];

        for (const selector of selectors) {
            const elements = document.querySelectorAll(selector);
            if (elements.length) {
                return elements[elements.length - 1].textContent;
            }
        }

        return '';
    };

    // Wait for ChatGPT to finish responding
    const waitForResponse = () => new Promise(resolve => {
        let started = false;
        let lastResponseText = '';
        let stableCount = 0;
        const MAX_WAIT_TIME = 300000; // 5 minutes
        const startTime = Date.now();
        let checkCount = 0;

        const checkResponse = setInterval(() => {
            checkCount++;

            // Periodically update status with wait time
            if (checkCount % 20 === 0) { // Every 10 seconds (20 * 500ms)
                const waitedTime = Math.floor((Date.now() - startTime) / 1000);
                showStatus(`Waiting for ChatGPT (${waitedTime}s)...`, 'info');
            }

            // Check if maximum wait time exceeded
            if (Date.now() - startTime > MAX_WAIT_TIME) {
                clearInterval(checkResponse);
                showStatus('Maximum wait time exceeded, capturing current response', 'warning');
                logger.warn(`Maximum wait time of ${MAX_WAIT_TIME}ms exceeded`);
                setTimeout(resolve, 1000);
                return;
            }

            // Check if response has started
            const thinking = isThinking();
            const hasResponses = document.querySelectorAll('[data-message-author-role="assistant"]').length > 0;

            if (thinking || hasResponses) {
                started = true;
                const currentResponseText = getResponseText();

                // Check if response has stabilized
                if (currentResponseText === lastResponseText) {
                    stableCount++;

                    if (!thinking && stableCount >= 10) {
                        clearInterval(checkResponse);
                        showStatus('Response complete, continuing...', 'success');
                        logger.success("Response stabilized and complete");
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
                showStatus('Timeout waiting for response', 'error');
                logger.warn("Timeout waiting for response to start");
                resolve();
            }
        }, 30000);
    });

    // Get the final response from ChatGPT
    const getChatGPTResponse = () => {
        logger.info("Getting final ChatGPT response");

        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) {
            logger.error("No ChatGPT response found");
            throw new Error('No ChatGPT response found');
        }

        const responseText = responses[responses.length - 1].textContent;
        logger.info(`Found response with ${responseText.length} characters`);
        return responseText;
    };

    // Send response back to the local server with retry
    const sendResponseToServerWithRetry = async (response) => {
        for (let attempt = 1; attempt <= CONFIG.RETRY_ATTEMPTS; attempt++) {
            try {
                await sendResponseToServer(response);
                return;
            } catch (error) {
                if (attempt < CONFIG.RETRY_ATTEMPTS) {
                    const delay = CONFIG.RETRY_DELAY * attempt; // Exponential backoff
                    showStatus(`Retrying to send response (attempt ${attempt})...`, 'warning');
                    logger.warn(`Send response attempt ${attempt} failed: ${error}. Retrying in ${delay/1000}s...`);
                    await new Promise(resolve => setTimeout(resolve, delay));
                } else {
                    throw error; // Rethrow after all retries fail
                }
            }
        }
    };

    // Send response back to the local server
    const sendResponseToServer = response => new Promise((resolve, reject) => {
        showStatus('Sending response back to server...', 'info');

        GM_xmlhttpRequest({
            method: 'POST',
            url: RESPONSE_URL,
            data: JSON.stringify({ response }),
            headers: { 'Content-Type': 'application/json' },
            timeout: 30000, // 30 second timeout
            onload: (response) => {
                if (response.status === 200) {
                    logger.success("Response sent successfully");
                    resolve();
                } else {
                    reject(`Server error: ${response.status} - ${response.statusText || 'Unknown error'}`);
                }
            },
            onerror: (error) => reject(`Connection error: ${error.message || 'Failed to connect'}`),
            ontimeout: () => reject('Connection timed out')
        });
    });

    // Main workflow
    const run = async () => {
        try {
            // Store start time for performance tracking
            const startTime = Date.now();

            // Wait for ChatGPT UI to load
            showStatus('Waiting for ChatGPT UI to load...', 'info');
            await waitForChatGPT();

            // Fetch content from server
            showStatus('Fetching content from Bear Notes...', 'info');
            const { content, question } = await fetchContentWithRetry();

            // Process content and get response
            showStatus('Processing content...', 'info');
            const response = await processContent(content, question);

            // Send response back to server
            await sendResponseToServerWithRetry(response);

            // Calculate total time
            const totalTime = ((Date.now() - startTime) / 1000).toFixed(2);
            showStatus(`Done! Processed in ${totalTime}s. Closing tab...`, 'success');

            // Close tab after a delay
            setTimeout(() => window.close(), CONFIG.AUTO_CLOSE_DELAY);
        } catch (err) {
            const errorMsg = err.message || err.toString() || 'Unknown error';
            showStatus(`Error: ${errorMsg}`, 'error');
            logger.error(`Bear to ChatGPT error: ${errorMsg}`);

            // Try to send error to server
            try {
                await sendResponseToServer(`ERROR: ${errorMsg}`);
            } catch (e) {
                logger.error(`Failed to send error to server: ${e}`);
            }
        }
    };

    // Start the process
    run();
})();