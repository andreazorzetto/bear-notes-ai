// ==UserScript==
// @name         Bear Notes to ChatGPT with Improved Performance
// @namespace    http://tampermonkey.net/
// @version      3.0
// @description  Auto-paste Bear Notes with optimized chunking and faster response handling
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

    // Config for chunking - increased initial size
    const CHUNK_SIZE_INITIAL = 50000; // Increased from 10000
    const CHUNK_SIZE_MIN = 1000;
    const CHUNK_REDUCTION_FACTOR = 0.7;

    // Chunking strategy templates
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

    // Prepare next chunk in the background
    const prepareNextChunkAsync = async (remainingContent, chunkSize) => {
        return new Promise(resolve => {
            setTimeout(() => {
                const nextChunk = remainingContent.substring(0, chunkSize);
                resolve(nextChunk);
            }, 0);
        });
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

    // Updated waitForResponse function with improved pattern matching
    const waitForResponse = () => new Promise(resolve => {
        let started = false;
        let lastResponseText = '';
        let stableCount = 0;
        let lastProgressUpdate = Date.now();
        let waitingDots = 0;
        const MAX_WAIT_TIME = 300000; // 5 minutes
        const startTime = Date.now();

        // Create observer to watch for changes in ChatGPT's responses
        const observer = new MutationObserver(mutations => {
            // Status updates
            const now = Date.now();
            if (now - lastProgressUpdate > 2000) {
                lastProgressUpdate = now;
                waitingDots = (waitingDots + 1) % 4;
                const dots = '.'.repeat(waitingDots);
                const elapsed = Math.floor((now - startTime) / 1000);

                if (isThinking()) {
                    showStatus(`ChatGPT is thinking${dots} (${elapsed}s)`);
                } else if (document.querySelectorAll('[data-message-author-role="assistant"]').length > 0) {
                    const responseLength = getResponseText().length;
                    showStatus(`Receiving response${dots} (${responseLength} chars, ${elapsed}s)`);
                }
            }

            // Check if maximum wait time exceeded
            if (Date.now() - startTime > MAX_WAIT_TIME) {
                observer.disconnect();
                showStatus('Maximum wait time exceeded, capturing current response');
                setTimeout(resolve, 1000);
                return;
            }

            // Force completion after reasonable time if final chunk was sent
            if (window.isFinalChunkSent && (Date.now() - startTime > 60000)) { // 1 minute wait max
                observer.disconnect();
                showStatus('Maximum wait time for final response exceeded, capturing current response');
                setTimeout(resolve, 1000);
                return;
            }

            // Check if response has started
            if (isThinking() || document.querySelectorAll('[data-message-author-role="assistant"]').length > 0) {
                started = true;
                const currentResponseText = getResponseText();

                // IMPROVED: More comprehensive acknowledgment patterns
                const acknowledgmentPatterns = [
                    /Received Chunk \d+\/\d+\.\s*Awaiting the (next|second|third|[\w\s]+) chunk/i,
                    /Acknowledged\.\s+Waiting for Chunk \d+\/\d+.*?before proceeding/i,
                    /Received Chunk \d+\/\d+/i,
                    /Waiting for (the )?Chunk \d+\/\d+/i,
                    /Chunk \d+\/\d+ received/i,
                    /Awaiting (the )?final part/i,
                    /Awaiting (the )?second chunk/i,
                    /Awaiting (the )?next chunk/i,
                    /ALL PARTS SENT.*?signal/i,
                    /CHATGPT RESPONSE:/i
                ];

                const isAcknowledgment = acknowledgmentPatterns.some(pattern =>
                    pattern.test(currentResponseText)
                );

                // IMPROVED: Check if this response contains ChatGPT's progress indicators
                const progressIndicators = [
                    /^Received Chunk/i,
                    /^Waiting for/i,
                    /^Chunk \d+\/\d+ received/i,
                    /^Awaiting/i,
                    /^Processing/i,
                    /^Analyzing/i
                ];

                const isProgressIndicator = progressIndicators.some(pattern =>
                    pattern.test(currentResponseText.trim())
                );

                // Check if this response contains the ALL PARTS SENT marker
                const hasAllPartsSent = currentResponseText.includes('ALL PARTS SENT');

                // Consider the final chunk sent if we see ALL PARTS SENT or the window flag is set
                const isFinalResponse = window.isFinalChunkSent || hasAllPartsSent;

                if (hasAllPartsSent && !window.isFinalChunkSent) {
                    window.isFinalChunkSent = true;
                    console.log('Found ALL PARTS SENT in response, waiting for final content');
                    stableCount = 0; // Reset stability counter for final content
                }

                // IMPROVED: Add an extra delay for multi-chunk processing
                if (isAcknowledgment && !isFinalResponse) {
                    stableCount = 0; // Reset stability - we're definitely not done
                    console.log('Detected acknowledgment message, continuing to wait...');
                    return; // Skip further processing for acknowledgment messages
                }

                // If we've sent the final chunk and the response is substantial
                if (window.isFinalChunkSent && !isAcknowledgment && !isProgressIndicator && currentResponseText.length > 200) {
                    // More likely to be the final response if longer than typical acknowledgments
                    stableCount += 2; // Accelerate stability detection for final responses
                }

                // Key improvement: Skip acknowledgment messages entirely if we're in multi-chunk mode
                // Only consider response stable if it's not an acknowledgment OR if this is the final chunk
                const shouldCheckStability = currentResponseText.length > 0 &&
                                             (!isAcknowledgment || isFinalResponse) &&
                                             (!isProgressIndicator || isFinalResponse);

                if (shouldCheckStability) {
                    if (currentResponseText === lastResponseText) {
                        stableCount++;

                        // More aggressive stability check for final response
                        const completionIndicators = document.querySelectorAll(
                            'button:not([disabled])[aria-label="Regenerate response"],' +
                            'button:not([disabled])[data-testid="regenerate-response-button"],' +
                            '.prose [id^="message-completion-status"]'
                        ).length > 0;

                        // Require more stability for final responses
                        const baseStabilityCount = Math.min(20, Math.max(10, Math.floor(currentResponseText.length / 500)));
                        const requiredStability = isFinalResponse ?
                                                 Math.ceil(baseStabilityCount * 1.5) : // 50% more for final
                                                 baseStabilityCount;

                        if (!isThinking() && (completionIndicators || stableCount >= requiredStability)) {
                            // If this is final content (not an acknowledgment) or we've sent the final chunk
                            if ((!isAcknowledgment && !isProgressIndicator) || isFinalResponse) {
                                observer.disconnect();
                                showStatus('Response complete, processing...');
                                setTimeout(resolve, 1000);
                            }
                        }
                    } else {
                        stableCount = 0;
                        lastResponseText = currentResponseText;
                    }
                }
            }
        });

        // Start observing
        const chatContainer = document.querySelector('main') || document.body;
        observer.observe(chatContainer, {
            childList: true, subtree: true, characterData: true, attributes: true
        });

        showStatus('Waiting for ChatGPT to respond...');

        // Timeout if response never starts
        setTimeout(() => {
            if (!started) {
                observer.disconnect();
                showStatus('No response detected after 30s, continuing...', true);
                resolve();
            }
        }, 30000);
    });

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

    // Get the final response from ChatGPT
    const getChatGPTResponse = () => {
        const responses = document.querySelectorAll('[data-message-author-role="assistant"]');
        if (!responses.length) throw new Error('No ChatGPT response found');
        return responses[responses.length - 1].textContent;
    };

    // Process content in chunks with improved formatting and parallel processing
    const processContent = async (content, question = "analyze the complete document and provide a comprehensive response") => {
        // Start overall timing
        Timer.start('ProcessContent');

        let remainingContent = content;
        let chunkSize = CHUNK_SIZE_INITIAL;
        let actualChunkNum = 0;
        let estimatedTotalChunks = estimateTotalChunks(content, chunkSize);
        let needsChunking = estimatedTotalChunks > 1;

        Logger.info(`Document size: ${content.length} characters`);
        Logger.info(`Initial chunk size: ${chunkSize} characters`);
        Logger.info(`Estimated chunks: ${estimatedTotalChunks}`);

        // If content fits in one message, send it directly with question
        if (!needsChunking) {
            Logger.info('Content fits in a single message');
            Timer.split('ProcessContent', 'PrepareMessage');

            showStatus('Content fits in a single message, preparing...');
            const singleMessage =
                `Please ${question}\n\n` +
                `===== BEGIN RAW NOTES DATA =====\n` +
                `${content}\n` +
                `===== END RAW NOTES DATA =====\n\n` +
                `The data above contains notes from various meetings and tickets. Based ONLY on this data, ${question}`;

            showStatus('Submitting content to ChatGPT...');
            Timer.split('ProcessContent', 'SubmittingMessage');
            window.isFinalChunkSent = true;
            await submitMessage(singleMessage);

            showStatus('Waiting for ChatGPT to respond...');
            const waitStartTime = performance.now();
            await waitForResponse();
            const waitTime = performance.now() - waitStartTime;
            Timer.split('ProcessContent', `WaitForResponse(${waitTime.toFixed(2)}ms)`);

            showStatus('Processing ChatGPT response...');
            const response = await getChatGPTResponse();
            Timer.split('ProcessContent', 'GetResponse');

            // Log metrics information
            const metrics = Timer.end('ProcessContent');
            showStatus(`Done! (${(metrics.total / 1000).toFixed(2)}s)`);

            Logger.success(`Processing completed in ${(metrics.total / 1000).toFixed(2)} seconds`);
            Logger.metrics([metrics]);

            return response;
        }

        // Multi-chunk processing...
        Logger.info(`Using multi-chunk approach (${estimatedTotalChunks} chunks)`);

        // Send initial message explaining the chunking process
        showStatus('Sending initial chunking message with the question...');
        Timer.split('ProcessContent', 'SendingInitialMessage');
        const initialMessage = formatMessage('initial', { totalChunks: estimatedTotalChunks, question: question });
        await submitMessage(initialMessage);
        await waitForResponse();
        Timer.split('ProcessContent', 'InitialMessageProcessed');

        // Process each chunk
        let actualChunks = [];
        let chunkMetrics = [];

        while (remainingContent.length > 0) {
            actualChunkNum++;
            const chunkTimerLabel = `Chunk${actualChunkNum}`;
            Timer.start(chunkTimerLabel);

            const isLastChunk = (remainingContent.length - chunkSize <= 0);

            // Start preparing the next chunk in parallel
            let nextChunkPromise = !isLastChunk ?
                prepareNextChunkAsync(remainingContent.substring(chunkSize), chunkSize) :
                Promise.resolve(null);

            showStatus(`Processing chunk ${actualChunkNum}/${estimatedTotalChunks}... (${remainingContent.length} chars remaining)`);
            Logger.info(`Processing chunk ${actualChunkNum}/${estimatedTotalChunks} (${remainingContent.length} chars remaining)`);

            // Extract the next chunk
            let currentChunk = remainingContent.substring(0, chunkSize);
            Timer.split(chunkTimerLabel, 'ChunkExtracted');

            // Format the chunk message
            let chunkMessage;
            if (isLastChunk) {
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
            Timer.split(chunkTimerLabel, 'ChunkFormatted');

            // Try to submit the chunk, reduce size if too large
            let success = false;
            let retryCount = 0;
            while (!success && chunkSize >= CHUNK_SIZE_MIN) {
                try {
                    retryCount++;
                    if (retryCount > 1) {
                        Logger.warning(`Retry ${retryCount-1} for chunk ${actualChunkNum} with size ${chunkSize}`);
                    }

                    Timer.split(chunkTimerLabel, `SubmitAttempt${retryCount}`);
                    if (isLastChunk) {
                        window.isFinalChunkSent = true;
                    }
                    success = await submitMessage(chunkMessage);

                    if (!success) {
                        // Reduce chunk size and try again
                        const oldSize = chunkSize;
                        chunkSize = Math.max(Math.floor(chunkSize * CHUNK_REDUCTION_FACTOR), CHUNK_SIZE_MIN);

                        showStatus(`Chunk too large, reducing to ${chunkSize} chars...`);
                        Logger.warning(`Chunk ${actualChunkNum} too large (${oldSize} chars), reducing to ${chunkSize} chars`);

                        // Recalculate the total chunks estimate
                        estimatedTotalChunks = Math.max(
                            estimatedTotalChunks,
                            actualChunkNum + Math.ceil(remainingContent.length / chunkSize)
                        );

                        // Recalculate the current chunk with new size
                        currentChunk = remainingContent.substring(0, chunkSize);
                        isLastChunk = (remainingContent.length <= chunkSize);

                        // Reformat with updated values
                        if (isLastChunk) {
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

                        // Try again with the smaller chunk
                        clearChatInput();
                    }
                } catch (err) {
                    Logger.error(`Error submitting chunk ${actualChunkNum}: ${err}`);
                    throw err;
                }
            }

            if (!success) {
                Logger.error(`Failed to submit chunk ${actualChunkNum} even at minimum size ${CHUNK_SIZE_MIN}`);
                throw new Error(`Failed to submit chunk even at minimum size ${CHUNK_SIZE_MIN}`);
            }

            // Wait for ChatGPT to process the chunk
            showStatus(`Waiting for ChatGPT to process chunk ${actualChunkNum}...`);
            Timer.split(chunkTimerLabel, 'WaitingForResponse');

            const chunkWaitStart = performance.now();
            await waitForResponse();
            const chunkWaitTime = performance.now() - chunkWaitStart;
            Timer.split(chunkTimerLabel, `ResponseReceived(${chunkWaitTime.toFixed(2)}ms)`);

            // Get the next chunk that was being prepared in parallel
            const nextChunk = await nextChunkPromise;
            Timer.split(chunkTimerLabel, 'NextChunkPrepared');

            // Store the processed chunk for tracking
            actualChunks.push(currentChunk);

            // Remove the processed chunk from remaining content
            remainingContent = remainingContent.substring(chunkSize);

            // Collect metrics for this chunk
            const chunkMetric = Timer.end(chunkTimerLabel);
            chunkMetrics.push(chunkMetric);

            Logger.success(`Chunk ${actualChunkNum} processed in ${(chunkMetric.total / 1000).toFixed(2)} seconds`);
        }

        // For the last chunk we already sent the "ALL PARTS SENT" message
        showStatus('Getting final response...');
        let response;
        let responseRetryCount = 0;
        const MAX_RESPONSE_RETRIES = 5;

        // Add retry loop for getting the final response
        while (responseRetryCount < MAX_RESPONSE_RETRIES) {
            response = await getChatGPTResponse();

            // Try to send the response
            try {
                // Check if this is a transitional message
                const transitionalPatterns = [
                    /Received Chunk \d+\/\d+.*?ALL PARTS SENT/i,
                    /Chunk \d+\/\d+.*?ALL PARTS SENT/i,
                    /--- End of Chunk \d+\/\d+ ---.*?ALL PARTS SENT/i
                ];

                const isTransitional = transitionalPatterns.some(pattern => pattern.test(response)) ||
                                      (response.includes('ALL PARTS SENT') && response.length < 300);

                if (isTransitional) {
                    responseRetryCount++;
                    Logger.warning(`Detected transitional message. Retrying (${responseRetryCount}/${MAX_RESPONSE_RETRIES})...`);
                    showStatus(`Waiting for final analysis... (retry ${responseRetryCount}/${MAX_RESPONSE_RETRIES})`);

                    // Wait for ChatGPT to complete its analysis
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    await waitForResponse();
                    continue;
                }

                // Try to send the response to the server
                let sendResult = await sendResponseToServer(response);
                if (sendResult && sendResult.shouldRetry) {
                    responseRetryCount++;
                    Logger.warning(`Server indicated retry needed (${responseRetryCount}/${MAX_RESPONSE_RETRIES})...`);
                    showStatus(`Waiting for complete response... (retry ${responseRetryCount}/${MAX_RESPONSE_RETRIES})`);

                    // Wait longer for ChatGPT to finish processing
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    await waitForResponse();
                    continue;
                }

                // If we got here, we successfully sent the response
                break;
            } catch (err) {
                // If there was an error that wasn't a retry request, rethrow it
                if (typeof err !== 'string' || !err.includes('acknowledgment')) {
                    throw err;
                }

                // Otherwise try again
                responseRetryCount++;
                Logger.warning(`Error with response, retrying (${responseRetryCount}/${MAX_RESPONSE_RETRIES}): ${err}`);
                showStatus(`Waiting for complete response... (retry ${responseRetryCount}/${MAX_RESPONSE_RETRIES})`);
                await new Promise(resolve => setTimeout(resolve, 2000));
                await waitForResponse();
            }
        }

        Timer.split('ProcessContent', 'FinalResponseReceived');

        // Log complete metrics
        const metrics = Timer.end('ProcessContent');
        chunkMetrics.push(metrics);

        showStatus(`Done! Processed ${actualChunkNum} chunks in ${(metrics.total / 1000).toFixed(2)}s`);

        Logger.success(`Processing completed in ${(metrics.total / 1000).toFixed(2)} seconds`);
        Logger.metrics(chunkMetrics);

        return response;
    };

    const sendResponseToServer = (response) => new Promise((resolve, reject) => {
        const metrics = Timer.getSummary();

        // More comprehensive patterns to detect transitional messages
        const transitionalPatterns = [
            /Chunk \d+\/\d+.*?ALL PARTS SENT/i,
            /of Chunk \d+\/\d+ ---ALL PARTS SENT/i,
            /End of Chunk.*?ALL PARTS SENT/i,
            /confirm, I've sent \d+ chunks/i
        ];

        const isTransitional = transitionalPatterns.some(pattern => pattern.test(response));

        // If this is a transitional message with ALL PARTS SENT
        if (isTransitional) {
            console.log('Detected transitional message with ALL PARTS SENT:', response);
            Logger.warning("Server detected transitional message. Need to wait for actual analysis.");

            // Return a special value instead of rejecting
            resolve({ needsMoreTime: true });
            return;
        }

        // Regular check for other acknowledgment patterns
        const acknowledgmentPatterns = [
            /Acknowledged\.\s+Waiting for Chunk \d+\/\d+/i,
            /Received Chunk \d+\/\d+/i,
            /Waiting for (the )?Chunk \d+\/\d+/i,
            /Chunk \d+\/\d+ received/i,
            /Awaiting (the )?final part/i,
            /Awaiting (the )?second chunk/i,
            /Awaiting (the )?next chunk/i,
            /before proceeding/i
        ];

        const isAcknowledgment = acknowledgmentPatterns.some(pattern => pattern.test(response));

        if (isAcknowledgment) {
            Logger.warning('Detected acknowledgment message, not sending to server');
            resolve({ needsMoreTime: true });
            return;
        }

        // Process a valid final response
        GM_xmlhttpRequest({
            method: 'POST',
            url: RESPONSE_URL,
            data: JSON.stringify({
                response,
                metrics: {
                    totalTime: metrics.find(m => m.label === 'ProcessContent')?.total || 0,
                    chunkCount: metrics.filter(m => m.label.startsWith('Chunk')).length,
                    detailedMetrics: metrics
                }
            }),
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

            // Add retry logic for handling transitional messages
            let finalResponse = response;
            let retryCount = 0;
            const MAX_RETRIES = 5;

            while (retryCount < MAX_RETRIES) {
                const result = await sendResponseToServer(finalResponse);

                if (result && result.needsMoreTime) {
                    retryCount++;
                    showStatus(`Waiting for complete analysis... (retry ${retryCount}/${MAX_RETRIES})`);
                    Logger.warning(`Detected transitional message, waiting for complete analysis (${retryCount}/${MAX_RETRIES})...`);

                    // Wait for ChatGPT to finish its analysis
                    await new Promise(resolve => setTimeout(resolve, 3000));
                    await waitForResponse();
                    finalResponse = await getChatGPTResponse();
                    continue;
                }

                // If we get here, the response was successfully sent
                break;
            }

            showStatus('Done! Closing tab...');
            setTimeout(() => window.close(), 2000);
        } catch (err) {
            showStatus(`Error: ${err.message || err}`, true);
            console.error('Bear to ChatGPT error:', err);
        }
    };

    // Add timing utility for tracking performance metrics
    const Timer = {
        timers: {},
        start: function(label) {
            this.timers[label] = {
                start: performance.now(),
                splits: []
            };
            console.log(`%c[TIMER] Started: ${label}`, 'color: #4CAF50; font-weight: bold;');
        },
        split: function(label, splitName) {
            if (!this.timers[label]) return;
            const now = performance.now();
            const elapsed = now - this.timers[label].start;
            this.timers[label].splits.push({
                name: splitName,
                time: elapsed
            });
            console.log(`%c[TIMER] ${label} - ${splitName}: ${elapsed.toFixed(2)}ms`, 'color: #2196F3;');
        },
        end: function(label) {
            if (!this.timers[label]) return;
            const now = performance.now();
            const elapsed = now - this.timers[label].start;
            console.log(`%c[TIMER] Ended: ${label} - Total: ${elapsed.toFixed(2)}ms`, 'color: #4CAF50; font-weight: bold;');

            // Return the timer data for reporting
            return {
                label,
                total: elapsed,
                splits: this.timers[label].splits
            };
        },
        // Get a formatted summary of all metrics
        getSummary: function() {
            let summary = [];
            for (const label in this.timers) {
                const timer = this.timers[label];
                const total = performance.now() - timer.start;
                summary.push({
                    label,
                    total,
                    splits: timer.splits
                });
            }
            return summary;
        }
    };

    // Enhanced console logging
    const Logger = {
        INFO: 'color: #2196F3; font-weight: bold;',
        SUCCESS: 'color: #4CAF50; font-weight: bold;',
        WARNING: 'color: #FF9800; font-weight: bold;',
        ERROR: 'color: #F44336; font-weight: bold;',

        info: function(message) {
            console.log(`%c[INFO] ${message}`, this.INFO);
        },

        success: function(message) {
            console.log(`%c[SUCCESS] ${message}`, this.SUCCESS);
        },

        warning: function(message) {
            console.log(`%c[WARNING] ${message}`, this.WARNING);
        },

        error: function(message) {
            console.log(`%c[ERROR] ${message}`, this.ERROR);
        },

        metrics: function(metrics) {
            console.group('%c[METRICS] Performance Report', 'color: #9C27B0; font-weight: bold;');

            console.table(metrics.map(m => ({
                Process: m.label,
                'Total Time (ms)': m.total.toFixed(2),
                'Steps': m.splits.length
            })));

            // Log detailed split information for each timer
            metrics.forEach(m => {
                if (m.splits.length > 0) {
                    console.group(`${m.label} - Detailed Steps`);
                    console.table(m.splits.map(s => ({
                        Step: s.name,
                        'Time (ms)': s.time.toFixed(2)
                    })));
                    console.groupEnd();
                }
            });

            console.groupEnd();
        }
    };

    // Start the process
    run();
})();