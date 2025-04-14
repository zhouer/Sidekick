# Sidekick Communication Protocol Specification

## 1. Introduction

This document specifies the **definitive communication protocol** used within the Sidekick ecosystem. It defines the structure and meaning of messages exchanged between the **Hero** (user's script/library) and the **Sidekick** frontend UI, typically relayed via the **Server** component. Adherence to this protocol is crucial for interoperability between components.

The protocol enables:
*   Peer Discovery & Status Management
*   Global Operations (affecting the entire UI state)
*   Module Control (creating, updating, removing UI elements)
*   Module Feedback (sending user events and errors back)

## 2. Transport Layer

*   **Mechanism:** WebSocket
*   **Default Endpoint:** `ws://localhost:5163` (Configurable via `sidekick.set_url()` and VS Code settings). The Server listens, Peers connect.
*   **Encoding:** JSON strings (UTF-8 encoded).

## 3. Message Format

All messages are JSON objects sharing this base structure:

```json
{
  "id": number,       // Reserved. Defaults to 0.
  "module": string,   // Target/Source module type (e.g., "grid", "system", "global").
  "type": string,     // Message type/action (e.g., "spawn", "announce", "event").
  "target"?: string,  // Target instance ID (Hero -> Sidekick for module control).
  "src"?: string,      // Source instance ID (Sidekick -> Hero for events/errors).
  "payload": object | null // Type-specific data. Keys MUST use camelCase (see below).
}
```

### 3.1 Field Descriptions

*   `id` (Integer): Reserved. Defaults to `0`.
*   `module` (String): Identifies the module type or system component (`grid`, `console`, `viz`, `canvas`, `control`, `system`, `global`).
*   `type` (String): Specifies the action (`spawn`, `update`, `remove`, `announce`, `event`, `error`, `clearAll`).
*   `target` (String, Optional): **Required** for `spawn`, `update`, `remove` messages from Hero. Identifies the target UI module instance.
*   `src` (String, Optional): **Required** for `event`, `error` messages from Sidekick. Identifies the source UI module instance.
*   `payload` (Object | Null): Contains type-specific data. **Crucially, see Section 3.2 regarding key casing.**

### 3.2 Payload `camelCase` Convention (CRITICAL)

**ALL keys within the `payload` object, and any nested objects inside it (like `options`, `config`, `valueRepresentation`, etc.), MUST use `camelCase` naming.**

*   **Example:** Use `numColumns`, `showInput`, `bgColor`, `strokeStyle`, `commandId`, `controlId`, `controlType`, `buttonText`, `valueRepresentation`, `variableName`.
*   **DO NOT USE:** `num_columns`, `show_input`, `bg_color`, `stroke_style`, `command_id`, `control_id`, `control_type`, `button_text`, `value_representation`, `variable_name` within the `payload`.

This convention ensures consistency between the JavaScript-based frontend/server and potentially other language libraries. Hero libraries (like `sidekick-py`) are responsible for converting their native conventions (e.g., `snake_case`) to `camelCase` before sending messages. Sidekick UI components expect to receive and send `camelCase` payloads. **Failure to adhere to this convention will likely result in commands or events being ignored or causing errors.**

## 4. Connection Lifecycle & Peer Discovery (`system` module)

Used by Peers (Hero/Sidekick) to announce their status and discover others via the Server.

### 4.1 Type: `announce`

*   **Direction:** Peer -> Server -> Other Peers
*   **Purpose:** Announce connection status (`online`/`offline`), role, version. Signals readiness.
*   **`target` / `src`:** Omitted.

### 4.2 `announce` Payload (Required Keys Marked)

```json
{
  "peerId": string,             // Required: Unique identifier for the peer instance (e.g., UUID).
  "role": "hero" | "sidekick",  // Required: Role of the announcing peer.
  "status": "online" | "offline", // Required: Current status.
  "version": string,            // Required: Version of the peer library/app.
  "timestamp": number           // Required: Timestamp (Unix epoch milliseconds).
}
```

### 4.3 Connection Flow & Disconnection

1.  Peer connects to Server.
2.  Peer sends `announce` (`status: "online"`) immediately.
3.  Server broadcasts this `online` announcement to *other* connected peers.
4.  Server sends a list of *currently online* peer announcements (history) **only to the newly connected peer**.
5.  Peers record other peers' status. Hero implementations **SHOULD** buffer non-`system` messages until receiving an `online` announce from a Sidekick peer.
6.  **Normal Disconnect:** Peer **SHOULD** send `announce` (`status: "offline"`) before closing. Server broadcasts it.
7.  **Abnormal Disconnect:** Server detects closure, generates and broadcasts an `offline` `announce` for the disconnected peer.

## 5. Global Operations (`global` module)

Affect the overall UI state, not a specific instance.

### 5.1 Type: `clearAll`

*   **Direction:** Hero -> Sidekick
*   **Purpose:** Instructs Sidekick to remove all active module instances.
*   **`target` / `src`:** Omitted.
*   **`payload`:** Null or omitted.

## 6. Core Module Interaction Message Types

Facilitate control and feedback for visual modules. Sent only after Hero confirms Sidekick is ready (via `system/announce`).

*   **Hero -> Sidekick:**
    *   `spawn`: Creates a new module instance. `target` required. Payload contains initial config.
    *   `update`: Modifies an existing instance. `target` required. Payload contains `action` and `options`.
    *   `remove`: Destroys an instance. `target` required. Payload usually null/omitted.
*   **Sidekick -> Hero:**
    *   `event`: Informs Hero of user actions/module events. `src` required. Payload contains event details.
    *   `error`: Reports an error encountered by Sidekick. `src` required. Payload contains error message.

## 7. Module-Specific Payloads (`payload` structure)

Defines the `payload` for `spawn`, `update`, and `event` types for each module. **Reminder: ALL keys within `payload` and nested objects MUST be `camelCase`.**

### 7.1 Module: `grid`

*   **`spawn` Payload:**
    ```json
    {
      "numColumns": number, // Required
      "numRows": number     // Required
    }
    ```
*   **`update` Payload:**
    *   `{ "action": "setColor", "options": { "x": number, "y": number, "color": string | null } }` (null clears color)
    *   `{ "action": "setText", "options": { "x": number, "y": number, "text": string | null } }` (null or "" clears text)
    *   `{ "action": "clearCell", "options": { "x": number, "y": number } }`
    *   `{ "action": "clear" }` (No `options` needed)
*   **`event` Payload:**
    ```json
    { "event": "click", "x": number, "y": number }
    ```

### 7.2 Module: `console`

*   **`spawn` Payload:**
    ```json
    {
      "showInput": boolean, // Required
      "text"?: string      // Optional initial text line
    }
    ```
*   **`update` Payload:**
    *   `{ "action": "append", "options": { "text": string } }`
    *   `{ "action": "clear" }`
*   **`event` Payload:** (Sent on input submission)
    ```json
    { "event": "inputText", "value": string }
    ```

### 7.3 Module: `viz`

*   **`spawn` Payload:** `{}` (Empty object)
*   **`update` Payload:**
    ```json
    {
      "action": string, // e.g., "set", "append", "setitem", "removeVariable"
      "variableName": string, // Required
      "options": { // Required
        // Optional fields depending on 'action':
        "path"?: Array<string | number>,
        "valueRepresentation"?: VizRepresentation | null, // See Section 8
        "keyRepresentation"?: VizRepresentation | null,   // See Section 8
        "length"?: number | null // For container size changes
      }
    }
    ```
*   **`event` Payload:** (None currently defined)

### 7.4 Module: `canvas`

*   **`spawn` Payload:**
    ```json
    {
        "width": number,   // Required
        "height": number,  // Required
        "bgColor"?: string // Optional background color
    }
    ```
*   **`update` Payload:**
    ```json
    {
      "action": string, // e.g., "clear", "config", "line", "rect", "circle"
      "options": object, // Required, structure depends on action (e.g., { x1, y1, x2, y2 })
      "commandId": string | number // Required: Unique ID for this command
    }
    ```
*   **`event` Payload:** (None currently defined)

### 7.5 Module: `control`

*   **`spawn` Payload:** `{}` (Empty object)
*   **`update` Payload:**
    *   Add Control:
        ```json
        {
          "action": "add", // Required
          "controlId": string, // Required: ID for the specific control
          "options": { // Required
            "controlType": "button" | "textInput", // Required
            "config": { // Required, content depends on controlType
              // e.g., for button: { "text": string }
              // e.g., for textInput: { "placeholder"?: string, "initialValue"?: string, "buttonText"?: string }
            }
          }
        }
        ```
    *   Remove Control:
        ```json
        {
          "action": "remove", // Required
          "controlId": string // Required
        }
        ```
*   **`event` Payload:** (Sent on user interaction)
    *   Button Click: ` { "event": "click", "controlId": string }`
    *   Text Input Submit: `{ "event": "inputText", "controlId": string, "value": string }`

## 8. Data Representation (`VizRepresentation`)

Structure used within `viz` module's `update` payload (`valueRepresentation`, `keyRepresentation`). **Keys MUST be `camelCase`.**

```typescript
interface VizRepresentation {
  type: string; // e.g., "int", "str", "list", "dict", "set", "object (ClassName)", "NoneType", "truncated", "recursive_ref", "error"
  value: any; // Primitive value, array of representations (for list/set), array of {key: VizRepresentation, value: VizRepresentation} (for dict), or string message
  length?: number; // For container types
  observableTracked?: boolean; // True if the original data was an ObservableValue
  id: string; // Required: Unique ID for this representation node (e.g., "str_12345_2")
}
```

## 9. Error Handling (`error` type message)

*   **Direction:** Sidekick -> Hero
*   **Structure:** Standard message format with `type: "error"`, `module` (e.g., `grid`), and `src` (instance ID).
*   **Payload:**
    ```json
    {
      "message": string // Required: Description of the error encountered by Sidekick.
    }
    ```

## 10. Versioning and Extensibility

*   This document defines the current protocol version.
*   Peers exchange version information via `system/announce`.
*   Implementations **SHOULD** be robust to receiving messages with extra, unexpected fields within the main structure or the `payload`.
*   Implementations **MUST** validate the presence and basic type of **required** fields (marked in payload definitions) for messages they process.
*   Adding new modules or actions requires updating this specification.