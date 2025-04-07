import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

// Helper function to generate a random nonce (same as before)
function getNonce() {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

/**
 * Generates the HTML content for the Sidekick Webview panel.
 *
 * Reads the built React app's index.html, adjusts asset paths using asWebviewUri,
 * and injects the necessary Content Security Policy (CSP) and script nonces.
 *
 * @param webview The VS Code Webview instance.
 * @param extensionUri The URI of the extension's root directory.
 * @returns The generated HTML string for the Webview.
 */
export function getWebviewContent(webview: vscode.Webview, extensionUri: vscode.Uri): string {
    // 1. Define the path to the built webapp's dist directory
    const webappDistPath = vscode.Uri.joinPath(extensionUri, 'dist');
    const indexHtmlPath = vscode.Uri.joinPath(webappDistPath, 'index.html');

    console.log(`[WebviewContent] Webapp dist path: ${webappDistPath.fsPath}`);
    console.log(`[WebviewContent] Reading index.html from: ${indexHtmlPath.fsPath}`);

    // 2. Read the built index.html file
    let htmlContent: string;
    try {
        htmlContent = fs.readFileSync(indexHtmlPath.fsPath, 'utf8');
    } catch (err) {
        const errorMsg = `Error reading webapp index.html: ${err}. Ensure 'npm run build' was executed in the 'webapp' directory.`;
        console.error(`[WebviewContent] ${errorMsg}`);
        // Provide a more informative error message in the webview itself
        return `<!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"><title>Error</title></head>
        <body>
            <h1>Error Loading Sidekick Frontend</h1>
            <p>Could not load the necessary files. Please check the extension's logs for details.</p>
            <p><strong>Details:</strong> ${errorMsg.replace(/</g, '<').replace(/>/g, '>')}</p>
            <p>Attempted to read: ${indexHtmlPath.fsPath.replace(/</g, '<').replace(/>/g, '>')}</p>
        </body>
        </html>`;
    }

    // 3. Generate a nonce for scripts
    const nonce = getNonce();

    // 4. Get WebSocket configuration for CSP
    const config = vscode.workspace.getConfiguration('sidekick.websocket');
    const wsPort = config.get<number>('port') ?? 5163;
    const wsHost = config.get<string>('host') ?? 'localhost';
    // Ensure wsHost doesn't contain invalid characters for CSP if it's user-configured
    const sanitizedWsHost = /^[a-zA-Z0-9\.\-]+$/.test(wsHost) ? wsHost : 'localhost'; // Basic sanitization
    const wsSource = `ws://${sanitizedWsHost}:${wsPort}`;

    // 5. Define the Content Security Policy (CSP) using the standard webview.cspSource
    //    This is the recommended approach by VS Code documentation.
    const csp = `
        default-src 'none';
        style-src ${webview.cspSource} 'unsafe-inline';
        script-src 'nonce-${nonce}' ${webview.cspSource};
        font-src ${webview.cspSource};
        connect-src ${wsSource};
        img-src ${webview.cspSource} data:;
    `.replace(/\s{2,}/g, ' ').trim(); // Clean up whitespace

    console.log(`[WebviewContent] Value of webview.cspSource used in CSP:`, webview.cspSource);
    console.log(`[WebviewContent] Final CSP string to be injected:`, csp);

    // 6. Replace asset paths (src/href starting with /assets/) with Webview URIs
    htmlContent = htmlContent.replace(/(src|href)="(\/assets\/[^"]+)"/g,
        (match, attr, assetPath) => {
            const assetUri = vscode.Uri.joinPath(webappDistPath, assetPath);
            const webviewUri = webview.asWebviewUri(assetUri);
            console.log(`[WebviewContent] Mapping asset path '${assetPath}' to webview URI '${webviewUri.toString()}'`);
            return `${attr}="${webviewUri}"`;
        }
    );

    // 7. Inject the CSP into the HTML's <head>
    //    This logic tries to replace an existing CSP meta tag first,
    //    and adds a new one if no existing tag is found.
    let cspInjected = false;
    htmlContent = htmlContent.replace(
        /(<meta\s+http-equiv="Content-Security-Policy"\s+content=")([^"]*)(">)/i, // Case-insensitive match
        (match, prefix, oldContent, suffix) => {
            cspInjected = true;
            console.log(`[WebviewContent] Replacing existing CSP meta tag.`);
            return `${prefix}${csp}${suffix}`;
        }
    );
    if (!cspInjected) {
        console.log(`[WebviewContent] No existing CSP meta tag found, adding new one.`);
        // Insert before the closing </head> tag
        htmlContent = htmlContent.replace(
            '</head>',
            `<meta http-equiv="Content-Security-Policy" content="${csp}"></head>`
        );
    }

    // 8. Add the nonce attribute to all script tags that have a src attribute
    //    This ensures external scripts loaded via asWebviewUri are allowed by the CSP.
    let nonceAdded = false;
    htmlContent = htmlContent.replace(/(<script\s+[^>]*?)(\s*src="[^"]*")(.*?>)/g, (match, prefix, srcAttr, suffix) => {
        // Avoid adding nonce if one already exists (e.g., from previous runs or manual edits)
        if (/\snonce=/.test(prefix) || /\snonce=/.test(suffix)) {
            return match;
        }
        nonceAdded = true;
        // Add the nonce attribute right after <script or before src
        return `${prefix} nonce="${nonce}"${srcAttr}${suffix}`;
    });
    if (nonceAdded) {
        console.log(`[WebviewContent] Added nonce to external script tag(s).`);
    } else {
        console.log(`[WebviewContent] No external script tags found needing nonce, or nonce already present.`);
    }


    console.log("[WebviewContent] Finished generating webview HTML.");
    return htmlContent;
}