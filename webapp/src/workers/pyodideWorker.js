// Web worker for running Python code with Pyodide
import { loadPyodide } from 'pyodide';

// Worker state
let pyodide = null;
let scriptPath = null;
let scriptContent = null;
let running = false;
let pyodideReady = false;
let sidekickMessageHandler = null;

// Send status to the main thread
function sendStatus(status, error = null) {
  self.postMessage({
    type: status,
    error: error,
  });
}

// Function to send messages from Python to JavaScript
function sendHeroMessage(message) {
  self.postMessage({
    type: 'sidekick',
    data: JSON.parse(message)
  });
}

// Function to register a handler for messages from JavaScript to Python
function registerSidekickMessageHandler(handler) {
  sidekickMessageHandler = handler;
}

// Initialize Pyodide
async function initializePyodide() {
  try {
    console.log('[pyodideWorker] initializePyodide: Loading Pyodide');

    // Load Pyodide
    pyodide = await loadPyodide({
      indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.23.4/full/'
    });

    console.log('[pyodideWorker] initializePyodide: Pyodide loaded');

    // Install required packages
    await pyodide.loadPackagesFromImports('import json, asyncio');

    console.log('[pyodideWorker] initializePyodide: Required packages installed');
    pyodideReady = true;

    // Fetch the script content
    await fetchScript();

    sendStatus('ready');
  } catch (error) {
    console.error('[pyodideWorker] initializePyodide: Error initializing Pyodide:', error);
    sendStatus('error', error.toString());
  }
}

// Fetch the Python script
async function fetchScript() {
  if (!scriptPath) {
    console.error('[pyodideWorker] fetchScript: No script path provided');
    sendStatus('error', 'No script path provided');
    return;
  }

  try {
    console.log(`[pyodideWorker] fetchScript: Fetching script: ${scriptPath}`);
    const response = await fetch('/' + scriptPath);

    if (!response.ok) {
      throw new Error(`Failed to fetch script: ${response.status} ${response.statusText}`);
    }

    scriptContent = await response.text();
    console.log('[pyodideWorker] fetchScript: Script fetched successfully');
  } catch (error) {
    console.error('[pyodideWorker] fetchScript: Error fetching script:', error);
    sendStatus('error', error.toString());
  }
}

// Run the Python script
async function runScript() {
  if (!pyodideReady || !scriptContent) {
    console.error('[pyodideWorker] runScript: Pyodide not ready or script not loaded');
    sendStatus('error', 'Pyodide not ready or script not loaded');
    return;
  }

  try {
    sendStatus('running');
    console.log('[pyodideWorker] runScript: Running script');
    running = true;

    // Expose the functions to Python
    self.sendHeroMessage = sendHeroMessage;
    self.registerSidekickMessageHandler = registerSidekickMessageHandler;

    // Run the script
    await pyodide.runPythonAsync(scriptContent);

    // If we reach here, the script completed successfully
    console.log('[pyodideWorker] runScript: Script completed');
    sendStatus('stopped');
    running = false;
  } catch (error) {
    console.error('[pyodideWorker] runScript: Error running script:', error);
    sendStatus('error', error.toString());
    running = false;
  }
}

// Stop the Python script
async function stopScript() {
  if (!running) {
    console.log('[pyodideWorker] stopScript: Script not running');
    return;
  }

  try {
    console.log('[pyodideWorker] stopScript: Stopping script');

    // Interrupt Python execution
    if (pyodide) {
      // Try to raise a KeyboardInterrupt exception
      await pyodide.runPythonAsync(`
        import signal
        signal.raise_signal(signal.SIGINT)
      `)
    }
  } catch (error) {
    if (error.toString().includes('KeyboardInterrupt')) {
      console.log('[pyodideWorker] stopScript: Script interrupted by user');
      sendStatus('terminated');
    } else {
      console.error('[pyodideWorker] stopScript: Error stopping script:', error);
      sendStatus('error', error.toString());
    }
    running = false;
  }
}

// Handle messages from the main thread
self.onmessage = async (event) => {
  const { data } = event;

  switch (data.type) {
    case 'init':
      // Initialize with script path
      scriptPath = data.scriptPath;

      // Initialize Pyodide
      await initializePyodide();
      break;

    case 'run':
      // Run the script
      if (!running) {
        await runScript();
      } else {
        console.warn('[pyodideWorker] self.onmessage: Script already running');
      }
      break;

    case 'stop':
      // Stop the script
      await stopScript();
      break;

    case 'sidekick':
      // Handle sidekick message from JavaScript to Python
      if (sidekickMessageHandler && pyodide) {
        try {
          // Call the registered handler with the message data
          sidekickMessageHandler(JSON.stringify(data.message));
        } catch (error) {
          console.error('[pyodideWorker] self.onmessage: Error handling sidekick message:', error);
        }
      }
      break;

    default:
      console.warn('[pyodideWorker] self.onmessage: Unknown message type:', data.type);
  }
};

// Handle errors
self.onerror = (error) => {
  if (error.toString().includes('KeyboardInterrupt')) {
    console.log('[pyodideWorker] self.onerror: Script interrupted by user');
    sendStatus('terminated');
    return;
  }

  console.error('[pyodideWorker] self.onerror: Worker error:', error);
  sendStatus('error', error.toString());
};
