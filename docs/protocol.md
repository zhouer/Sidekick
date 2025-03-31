# Sidekick Communication Protocol Specification

## 1. Introduction

This document specifies the communication protocol between the **Hero** (user's script using the `sidekick` Python library) and the **Sidekick** frontend (React application). This protocol enables the Hero to control visual modules in the Sidekick UI and allows Sidekick to send notifications back to the Hero.

## 2. Transport Layer

*   **Mechanism:** WebSocket
*   **Default Endpoint:** `ws://localhost:5163` (Configurable via `sidekick.set_url()`).
*   **Encoding:** JSON strings (UTF-8 encoded).
*   **Keep-Alive:** The Python client uses WebSocket Ping/Pong frames for connection maintenance and failure detection. The server should respond to Pings with Pongs.

## 3. Message Format

All messages exchanged between Hero and Sidekick share a common JSON structure.

### 3.1 Hero -> Sidekick Message Structure

These messages are commands sent from the Hero script to control the Sidekick UI modules.

```json
{
  "id": number,       // Reserved for future use (e.g., message correlation). Currently defaults to 0.
  "module": string,   // Target module type ("grid", "console", "viz", "canvas", "control").
  "method": string,   // The action to perform ("spawn", "update", "remove").
  "target": string,   // Unique identifier of the target module instance.
  "payload": object | null // Data specific to the method and module type. Null if no payload is needed.
}
```

### 3.2 Sidekick -> Hero Message Structure

These messages are notifications or error reports sent from the Sidekick UI back to the Hero script.

```json
{
  "id": number,       // Reserved for future use. Currently defaults to 0.
  "module": string,   // Source module type that generated the message ("grid", "console", "control").
  "method": string,   // The type of message ("notify", "error").
  "src": string,      // Unique identifier of the source module instance.
  "payload": object | null // Data specific to the notification or error.
}
```

### 3.3 Field Descriptions

*   `id` (Integer): Reserved. Defaults to `0`. Future versions might use this for request/response matching.
*   `module` (String): Identifies the type of module involved (e.g., `"grid"`, `"console"`, `"viz"`, `"canvas"`, `"control"`).
*   `method` (String): Specifies the action (for Hero->Sidekick) or the message type (for Sidekick->Hero).
*   `target` (String): **Hero -> Sidekick only.** The unique ID of the module instance that should process the command.
*   `src` (String): **Sidekick -> Hero only.** The unique ID of the module instance that originated the message.
*   `payload` (Object | Null): Contains method-specific data structures, detailed in Section 5.

## 4. Core Methods

These define the primary interactions possible via the `method` field.

### 4.1 Hero -> Sidekick Methods

*   **`spawn`**: Instructs Sidekick to create and display a new instance of a specified module type. The `payload` contains the initial configuration for the module.
*   **`update`**: Instructs Sidekick to modify the state of an existing module instance (identified by `target`). The `payload` contains the specific changes to apply. For the `viz` module, this handles all variable additions, updates, and removals. For the `control` module, it handles adding/removing individual controls.
*   **`remove`**: Instructs Sidekick to destroy and remove a specific module instance (identified by `target`) from the UI.

### 4.2 Sidekick -> Hero Methods

*   **`notify`**: Sent by interactive modules (like `grid`, `console`, or `control`) to inform the Hero about user actions (e.g., cell click, text input submission, button click). The `payload` contains details about the event.
*   **`error`**: Sent by Sidekick if it encounters an error while processing a command or managing a module (e.g., invalid payload, module not found). The `payload` typically includes an error message.

## 5. Module-Specific Payloads (`payload` structure)

This section details the expected structure of the `payload` object for different `module` and `method` combinations.

### 5.1 Module: `grid`

*   **`spawn` Payload:**
    ```json
    { "size": [width: number, height: number] }
    ```
*   **`update` Payload (Choose one format):**
    *   Update single cell:
        ```json
        { "x": number, "y": number, "color"?: string | null, "text"?: string | null }
        ```
    *   Fill entire grid:
        ```json
        { "fill_color": string }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    { "event": "click", "x": number, "y": number }
    ```

### 5.2 Module: `console`

*   **`spawn` Payload:**
    ```json
    { "text"?: string } // Optional initial text line
    ```
*   **`update` Payload (Choose one format):**
    *   Append text: ` { "text": string } `
    *   Clear console: ` { "clear": true } `
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    { "event": "submit", "value": string } // User submitted text
    ```

### 5.3 Module: `viz`

*   **`spawn` Payload:**
    ```json
    {} // No specific payload needed on spawn
    ```
*   **`update` Payload:** Handles variable add/update/remove.
    ```json
    {
      "variable_name": string,
      "change_type": string, // "set", "setitem", "append", ..., "remove_variable"
      "path": Array<string | number>, // `[]` for root
      "value_representation": VizRepresentation | null, // See Section 6. Null if not applicable
      "key_representation"?: VizRepresentation | null,   // Optional: For dict ops
      "length"?: number | null                   // Optional: New container length
    }
    ```

### 5.4 Module: `canvas`

*   **`spawn` Payload:**
    ```json
    { "width": number, "height": number, "bgColor"?: string }
    ```
*   **`update` Payload:** Represents a single drawing or configuration command.
    ```json
    {
      "command": string, // "clear", "config", "line", "rect", "circle"
      "options": object, // Command-specific parameters
      "commandId": string | number // Unique ID for this command
    }
    ```
    *   *(See specific command options in previous documentation)*

### 5.5 Module: `control`

*   **`spawn` Payload:**
    ```json
    {} // No specific payload needed, creates an empty container
    ```
*   **`update` Payload:** Used to add or remove individual controls.
    ```json
    {
      "operation": "add" | "remove", // The action to perform
      "control_id": string,         // Unique ID for the specific control within this module
      // Required for "add" operation:
      "control_type"?: "button" | "text_input",
      "config"?: {
        // For "button":
        "text"?: string,         // Button label
        // For "text_input":
        "placeholder"?: string, // Input placeholder
        "initial_value"?: string,// Input initial value
        "button_text"?: string  // Submit button text (optional)
      }
    }
    ```
*   **`notify` Payload (Sidekick -> Hero):** Sent on user interaction.
    ```json
    {
      "event": "click" | "submit", // "click" for button, "submit" for text_input
      "control_id": string,         // ID of the interacted control
      // Present only for "submit" event from text_input:
      "value"?: string              // The submitted text value
    }
    ```

## 6. Data Representation (`VizRepresentation`)

This standard JSON structure is used within the `payload` of `viz` module `update` messages (`value_representation`, `key_representation`) to serialize Python data for frontend display.

A `VizRepresentation` is a JSON object with the following fields:

*   `type` (String): Python type name or special type identifier (e.g., `"int"`, `"list"`, `"dict"`, `"set"`, `"NoneType"`, `"object (ClassName)"`, `"repr (ClassName)"`, `"truncated"`).
*   `id` (String): Unique identifier for this data node representation (e.g., `"int_1401..."`, `"obs_1401..."`).
*   `value` (Any): The serialized value (primitive, array of representations, object mapping names to representations, or descriptive string).
*   `length` (Integer | undefined): Item/attribute count for container types.
*   `observable_tracked` (Boolean | undefined): `true` if the data originated from an `ObservableValue`.

*(Detailed value structures for list, dict, object omitted for brevity - see previous Viz documentation)*

## 7. Error Handling

Sidekick -> Hero `error` messages use the standard structure with `method: "error"`. The `payload` typically contains:

```json
{ "message": string } // Description of the error encountered by Sidekick
```

## 8. Versioning and Extensibility

This protocol definition represents the current version. Future changes may occur.
*   Implementations should be robust to receiving messages with extra, unexpected fields.
*   Implementations should strictly require the presence of mandatory fields defined herein.
*   There is currently no formal version negotiation mechanism. Compatibility relies on adherence to this specification.