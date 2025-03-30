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
"module": string,   // Target module type (e.g., "grid", "console", "viz", "canvas").
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
"module": string,   // Source module type that generated the message (e.g., "grid", "console").
"method": string,   // The type of message ("notify", "error").
"src": string,      // Unique identifier of the source module instance.
"payload": object | null // Data specific to the notification or error.
}
```

### 3.3 Field Descriptions

*   `id` (Integer): Reserved. Defaults to `0`. Future versions might use this for request/response matching.
*   `module` (String): Identifies the type of module involved (e.g., `"grid"`, `"console"`, `"viz"`, `"canvas"`).
*   `method` (String): Specifies the action (for Hero->Sidekick) or the message type (for Sidekick->Hero).
*   `target` (String): **Hero -> Sidekick only.** The unique ID of the module instance that should process the command.
*   `src` (String): **Sidekick -> Hero only.** The unique ID of the module instance that originated the message.
*   `payload` (Object | Null): Contains method-specific data structures, detailed in Section 5.

## 4. Core Methods

These define the primary interactions possible via the `method` field.

### 4.1 Hero -> Sidekick Methods

*   **`spawn`**: Instructs Sidekick to create and display a new instance of a specified module type. The `payload` contains the initial configuration for the module.
*   **`update`**: Instructs Sidekick to modify the state of an existing module instance (identified by `target`). The `payload` contains the specific changes to apply. For the `viz` module, this handles all variable additions, updates, and removals.
*   **`remove`**: Instructs Sidekick to destroy and remove a specific module instance (identified by `target`) from the UI.

### 4.2 Sidekick -> Hero Methods

*   **`notify`**: Sent by interactive modules (like `grid` or `console`) to inform the Hero about user actions (e.g., cell click, text input submission). The `payload` contains details about the event.
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
        {
        "x": number,
        "y": number,
        "color"?: string | null, // Optional: New background color (null to clear?)
        "text"?: string | null   // Optional: New text content (null to clear?)
        }
        ```
    *   Fill entire grid:
        ```json
        { "fill_color": string } // Color to fill all cells
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
    *   Append text:
        ```json
        { "text": string } // Text to append (can include newlines)
        ```
    *   Clear console:
        ```json
        { "clear": true }
        ```
*   **`notify` Payload (Sidekick -> Hero):**
    ```json
    { "event": "submit", "value": string } // User submitted text
    ```

### 5.3 Module: `viz`

*   **`spawn` Payload:**
    ```json
    {} // No specific payload needed on spawn
    ```
*   **`update` Payload:** This single method handles adding, updating, and removing variables.
    ```json
    {
    "variable_name": string,                 // Name of the variable to operate on
    "change_type": string,                   // Type of change: "set", "setitem", "append", "pop", "insert", "delitem", "remove", "add_set", "discard_set", "clear", "remove_variable"
    "path": Array<string | number>,          // Path within the variable structure where change occurred. `[]` targets the root variable.
    "value_representation": VizRepresentation | null, // Representation of the new value (or added element, or cleared container). Null if not applicable (e.g., remove_variable, pop, delitem). See Section 6.
    "key_representation"?: VizRepresentation | null,   // Optional: Representation of the key involved in dict operations (setitem, delitem).
    "length"?: number | null                   // Optional: New length of container after the operation.
    }
    ```

### 5.4 Module: `canvas`

*   **`spawn` Payload:**
    ```json
    {
    "width": number,          // Canvas width in pixels
    "height": number,         // Canvas height in pixels
    "bgColor"?: string        // Optional: Initial background color (CSS format)
    }
    ```
*   **`update` Payload:** Represents a single drawing or configuration command.
    ```json
    {
    "command": string,        // Command name: "clear", "config", "line", "rect", "circle"
    "options": object,        // Command-specific parameters (see below)
    "commandId": string | number // Unique ID for this specific command instance (ensured by Hero or Sidekick)
    }
    ```
    *   **`command: "clear"` Options:** `{ "color"?: string }` (Optional color, defaults to bg)
    *   **`command: "config"` Options:** `{ "strokeStyle"?: string, "fillStyle"?: string, "lineWidth"?: number }`
    *   **`command: "line"` Options:** `{ "x1": number, "y1": number, "x2": number, "y2": number }`
    *   **`command: "rect"` Options:** `{ "x": number, "y": number, "width": number, "height": number, "filled"?: boolean }`
    *   **`command: "circle"` Options:** `{ "cx": number, "cy": number, "radius": number, "filled"?: boolean }`

## 6. Data Representation (`VizRepresentation`)

This standard JSON structure is used within the `payload` of `viz` module `update` messages, specifically in the `value_representation` and `key_representation` fields, to serialize Python data for frontend display.

A `VizRepresentation` is a JSON object with the following fields:

*   `type` (String): Python type name (e.g., `"int"`, `"list"`, `"dict"`, `"set"`, `"NoneType"`) or a special type identifier (e.g., `"object (ClassName)"`, `"repr (ClassName)"`, `"truncated"`, `"error"`, `"recursive_ref"`).
*   `id` (String): A unique identifier for this specific data node representation (e.g., `"int_1401..._0"`, `"obs_1401..."`). Helps the frontend with rendering keys and potentially tracking changes.
*   `value` (Any): The serialized value.
    *   For **Primitives** (`int`, `float`, `bool`, `str`): The actual primitive value.
    *   For **`NoneType`**: The string `"None"`.
    *   For **`list`**, **`set`**: An array (`[]`) containing nested `VizRepresentation` objects for each element.
    *   For **`dict`**: An array (`[]`) of objects, where each object has the structure `{ "key": VizRepresentation, "value": VizRepresentation }`.
    *   For **`object`**: An object (`{}`) mapping attribute names (strings) to their corresponding nested `VizRepresentation` objects.
    *   For **`repr`**: A string containing the result of Python's `repr()` function (used as fallback).
    *   For **Special Types** (`truncated`, `error`, `recursive_ref`): A descriptive string.
*   `length` (Integer | undefined): For container types (`list`, `dict`, `set`, `object`), this indicates the number of elements or attributes represented. Undefined for non-container types.
*   `observable_tracked` (Boolean | undefined): Set to `true` if this representation corresponds to data that originated directly from an `ObservableValue`. Undefined otherwise. Helps the frontend apply specific styling or behavior.

## 7. Error Handling

Sidekick -> Hero `error` messages use the standard structure with `method: "error"`. The `payload` typically contains:

```json
{ "message": string } // Description of the error encountered by Sidekick
```

## 8. Versioning and Extensibility

This protocol definition represents the current version. Future changes may occur.
*   Implementations should be robust to receiving messages with extra, unexpected fields in the `payload`.
*   Implementations should strictly require the presence of mandatory fields defined in this specification.
*   There is currently no formal version negotiation mechanism in the protocol itself. Compatibility relies on adherence to this specification.