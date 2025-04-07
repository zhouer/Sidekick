import vscode from 'vscode';
import { createOrShowSidekickPanel } from './webviewPanel';
import { stopWebSocketServer } from './websocketServer';

export function activate(context: vscode.ExtensionContext) {
    console.log('Activating sidekick-vscode');
    let disposable = vscode.commands.registerCommand('sidekick.show', () => {
        // Pass context here
        createOrShowSidekickPanel(context.extensionUri, context);
    });
    context.subscriptions.push(disposable);
}

export function deactivate(): Promise<void> {
    console.log('Deactivating sidekick-vscode');
    return stopWebSocketServer();
}