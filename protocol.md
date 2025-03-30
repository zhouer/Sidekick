# Sidekick Communication Protocol Specification

## 1. Introduction

This document specifies the communication protocol between the **Hero** (user's script using the `sidekick` Python library) and the **Sidekick** frontend (React application). This protocol enables the Hero to control visual modules in the Sidekick UI and allows Sidekick to send notifications back to the Hero.

## 2. Transport Layer

*   **Mechanism:** WebSocket
*   **Default Endpoint:** `ws://localhost:5163` (Configurable via `sidekick.set_url()`).
*   **Encoding:** JSON strings.
*   **Keep-Alive:** The Python client uses WebSocket Ping/Pong frames for connection maintenance and failure detection.

## 3. Message Format

All messages share a common JSON structure.

### 3.1 Hero -> Sidekick Message Structure

(Commands from Hero to control Sidekick UI)

```json
{
"id": number,       // Reserved (defaults to 0).
"module": string,   // Target module type ("grid", "console", "viz", "canvas").
"method": string,   // Action ("spawn", "update", "remove", "remove_var").
"target": string,   // Unique ID of the target module instance.
"payload": object|null // Method-specific data.
}
```

### 3.2 Sidekick -> Hero Message Structure

(Notifications/Errors from Sidekick UI back to Hero)

```json
{
"id": number,       // Reserved (defaults to 0).
"module": string,   // Source module type ("grid", "console").
"method": string,   // Message type ("notify", "error").
"src": string,      // Unique ID of the source module instance.
"payload": object|null // Notification/error specific data.
}
```

### 3.3 Field Descriptions

*   `id`: (Integer) Reserved. Defaults to `0`.
*   `module`: (String) Module type (`"grid"`, `"console"`, `"viz"`, `"canvas"`).
*   `method`: (String) Action or message type.
*   `target`: (String) **Hero -> Sidekick only.** Target instance ID.
*   `src`: (String) **Sidekick -> Hero only.** Source instance ID.
*   `payload`: (Object | Null) Method-specific data.

## 4. Core Methods

*   **`spawn`** (Hero -> Sidekick): Creates a module instance. Payload contains initial config.
*   **`update`** (Hero -> Sidekick): Modifies an existing instance. Payload contains state changes or commands.
*   **`remove`** (Hero -> Sidekick): Destroys a module instance.
*   **`remove_var`** (Hero -> Sidekick): Specific to `viz`, removes a variable display. Payload: `{ "variable_name": string }`.
*   **`notify`** (Sidekick -> Hero): Sends event information (e.g., user input). Payload depends on the source module.
*   **`error`** (Sidekick -> Hero): Reports an error. Payload typically includes `{ "message": string }`.

## 5. Module-Specific Payloads

### 5.1 Module: `grid`

*   **`spawn` Payload:** `{ "size": [width: number, height: number] }`
*   **`update` Payload:**
    *   Cell: `{ "x": number, "y": number, "color"?: string|null, "text"?: string|null }`
    *   Fill: `{ "fill_color": string }` (Optional)
*   **`notify` Payload:** `{ "event": "click", "x": number, "y": number }`

### 5.2 Module: `console`

*   **`spawn` Payload:** `{ "text"?: string }`
*   **`update` Payload:**
    *   Append: `{ "text": string }`
    *   Clear: `{ "clear": true }`
*   **`notify` Payload:** `{ "event": "submit", "value": string }` (User input)

### 5.3 Module: `viz`

*   **`spawn` Payload:** `{}`
*   **`update` Payload:**
    *   `variable_name`: `string` (Required)
    *   `representation`: `VizRepresentation` (Required - See Section 6)
    *   `change_type`: `string` (Optional - Hint: `"replace"`, `"observable_update"`)
    *   `change_details`: `object` (Optional - Context, e.g., `{ "_obs_value_id": string }`)
*   **`remove_var` Payload:** `{ "variable_name": string }` (Required)

### 5.4 Module: `canvas`

*   **`spawn` Payload:** `{ "width": number, "height": number, "bgColor"?: string }`
*   **`update` Payload:** `{ "command": string, "options": object }`
    *   `command: "clear"`, `options: { "color"?: string }`
    *   `command: "config"`, `options: { "strokeStyle"?: string, "fillStyle"?: string, "lineWidth"?: number }`
    *   `command: "line"`, `options: { "x1": number, "y1": number, "x2": number, "y2": number }`
    *   `command: "rect"`, `options: { "x": number, "y": number, "width": number, "height": number, "filled"?: boolean }`
    *   `command: "circle"`, `options: { "cx": number, "cy": number, "radius": number, "filled"?: boolean }`

## 6. Data Representation (`VizRepresentation`)

Used within the `payload` of `viz` module `update` messages.

A `VizRepresentation` is a JSON object:

*   `type`: (String) Python type name or special type (e.g., `"int"`, `"list"`, `"dict"`, `"set"`, `"object (ClassName)"`, `"truncated"`).
*   `id`: (String) Unique ID for this representation node.
*   `value`:
    *   Primitive: The actual value.
    *   `NoneType`: String `"None"`.
    *   `list`, `set`: Array `[]` of nested `VizRepresentation`.
    *   `dict`: Array `[]` of `{ "key": VizRepresentation, "value": VizRepresentation }`.
    *   `object`: Object `{}` mapping attr names to `VizRepresentation`, or `repr()` string.
    *   Special types: Descriptive string.
*   `length`: (Integer | undefined) Item/attribute count.
*   `observable_tracked`: (Boolean | undefined) `true` if data originated from an `ObservableValue`.

## 7. Error Handling

Sidekick -> Hero `error` messages use payload `{ "message": string }`.

## 8. Versioning and Extensibility

This protocol may evolve. Implementations should handle required fields and tolerate extra fields. No formal version negotiation exists currently.