# Sidekick Communication Protocol Specification

## 1. Introduction

This document specifies the communication protocol between the **Hero** (user's script using the `sidekick` library) and the **Sidekick** frontend (React application). This protocol enables the Hero to control visual modules in the Sidekick UI and allows Sidekick to send notifications back to the Hero.

## 2. Transport Layer

*   **Mechanism:** WebSocket
*   **Default Endpoint:** `ws://localhost:5163` (Configurable via `sidekick.set_url()`).
*   **Encoding:** JSON strings (UTF-8 encoded).
*   **Keep-Alive:** The Python client uses WebSocket Ping/Pong frames for connection maintenance and failure detection (after disabling underlying socket timeout). The server should respond to Pings with Pongs.

## 3. Message Format

All messages exchanged between Hero and Sidekick share a common JSON structure.

### 3.1 Hero -> Sidekick Message Structure

These messages are commands sent from the Hero script to control the Sidekick UI modules.

```json
{
  "id": number,       // Reserved. Defaults to 0.
  "module": string,   // Target module type (e.g., "grid", "console", "viz", "canvas", "control").
  "method": string,   // The action to perform ("spawn", "update", "remove").
  "target": string,   // Unique identifier of the target module instance.
  "payload": object | null // Data specific to the method and module type. Null if no payload.
}
```

### 3.2 Sidekick -> Hero Message Structure

These messages are notifications or error reports sent from the Sidekick UI back to the Hero script.

```json
{
  "id": number,       // Reserved. Defaults to 0.
  "module": string,   // Source module type (e.g., "grid", "console", "control").
  "method": string,   // The type of message ("notify", "error").
  "src": string,      // Unique identifier of the source module instance.
  "payload": object | null // Data specific to the notification or error. Null if no payload.
}
```

### 3.3 Field Descriptions

*   `id` (Integer): Reserved. Defaults to `0`.
*   `module` (String): Identifies the type of module involved.
*   `method` (String): Specifies the action (Hero->Sidekick) or message type (Sidekick->Hero).
*   `target` (String): **Hero -> Sidekick only.** The unique ID of the target module instance.
*   `src` (String): **Sidekick -> Hero only.** The unique ID of the source module instance.
*   `payload` (Object | Null): Contains method-specific data structures, detailed in Section 5.

## 4. Core Methods

These define the primary interactions possible via the `method` field.

### 4.1 Hero -> Sidekick Methods

*   **`spawn`**: Creates a new module instance. Payload contains initial configuration.
*   **`update`**: Modifies an existing module instance. Payload contains specific changes.
*   **`remove`**: Destroys a module instance.

### 4.2 Sidekick -> Hero Methods

*   **`notify`**: Informs Hero about user actions. Payload contains event details.
*   **`error`**: Reports an error encountered by Sidekick. Payload contains error message.

## 5. Module-Specific Payloads (`payload` structure)

This section details the expected structure of the `payload` object for different `module` and `method` combinations.

### 5.1 Module: `grid`

*   **`spawn` Payload:**
    ```json
    {
      "size": [width: number, height: number]
    }
    ```
*   **`update` Payload:**
    *   Set individual cell state:
        ```json
        {
          "action": "setCell",
          "options": {
            "x": number,
            "y": number,
            "color"?: string | null,
            "text"?: string | null
          }
        }
        ```
    *   Clear the entire grid:
        ```json
        {
          "action": "clear"
          // No options needed
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "click",
      "x": number,
      "y": number
    }
    ```

### 5.2 Module: `console`

*   **`spawn` Payload:**
    ```json
    {
      "text"?: string // Optional initial text line
    }
    ```
*   **`update` Payload:**
    *   Append text line(s):
        ```json
        {
          "action": "append",
          "options": {
            "text": string // The text line(s) to append
          }
        }
        ```
    *   Clear the console output:
        ```json
        {
          "action": "clear"
          // No options needed
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "submit",
      "value": string
    }
    ```

### 5.3 Module: `viz`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:** Handles variable add/update/remove.
    ```json
    {
      "action": string,       // e.g., "set", "setitem", "append", "removeVariable"
      "variableName": string, // The name of the variable being updated
      "options": {            // Parameters specific to the action
        "path"?: Array<string | number>, // Required for non-root actions
        "valueRepresentation"?: VizRepresentation | null, // New value (if applicable)
        "keyRepresentation"?: VizRepresentation | null,   // Key (for dict setitem)
        "length"?: number | null                   // New length (for container ops)
        // Note: For action="removeVariable", options might be empty or omitted.
      }
    }
    ```

### 5.4 Module: `canvas`

*   **`spawn` Payload:**
    ```json
    {
      "width": number,
      "height": number,
      "bgColor"?: string
    }
    ```
*   **`update` Payload:**
    ```json
    {
      "action": string, // e.g., "clear", "config", "line", "rect", "circle"
      "options": object, // Command-specific parameters (e.g., {x1, y1, x2, y2} for line)
      "commandId": string | number // REQUIRED: Unique ID for this command instance
    }
    ```
    *   *(Example options: `clear: { color? }`, `config: { strokeStyle?, fillStyle?, lineWidth? }`, `line: { x1, y1, x2, y2 }`, etc.)*

### 5.5 Module: `control`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:** Used to add or remove individual controls.
    *   Add a control:
        ```json
        {
          "action": "add",
          "controlId": string, // ID of the control to add
          "options": {        // Parameters for the new control
            "controlType": "button" | "text_input",
            "config": {
              "text"?: string,         // For button
              "placeholder"?: string, // For text_input
              "initialValue"?: string,// For text_input
              "buttonText"?: string  // For text_input
            }
          }
        }
        ```
    *   Remove a control:
        ```json
        {
          "action": "remove",
          "controlId": string // ID of the control to remove
          // No options needed for removal
        }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    {
      "event": "click" | "submit",
      "controlId": string,
      "value"?: string // Present only for "submit" event
    }
    ```

## 6. Data Representation (`VizRepresentation`)

(No changes needed here, definition remains the same, keys are already camelCase)

*   `type` (String)
*   `id` (String)
*   `value` (Any)
*   `length` (Integer | undefined)
*   `observableTracked` (Boolean | undefined)

## 7. Error Handling

Sidekick -> Hero `error` messages use the standard structure with `method: "error"`. The `payload` typically contains:

```json
{ "message": string }
```

## 8. Versioning and Extensibility

This protocol definition represents the current version. Future changes may occur.
*   Implementations should be robust to receiving messages with extra, unexpected fields.
*   Implementations should strictly require the presence of mandatory fields defined herein (e.g., `commandId` for Canvas updates, `action` for most updates).
*   Keys within the `payload` object MUST use `camelCase`.
*   There is currently no formal version negotiation mechanism.