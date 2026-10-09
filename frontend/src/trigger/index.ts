// Trigger module — sending messages (M4 phase 05).
// The TriggerPanel modal is the only entry point; reach it via
// the "+ Send" button in the project header, or via the "Send"
// button in a host's side panel (pre-filled source).

export { TriggerPanel } from './TriggerPanel';
export { TriggerAPI } from './api';
export type { Hop, RouteResponse, RouteError, SendResult, MessageRow, MessagesResponse } from './types';
export type { Protocol } from './TriggerPanel';
