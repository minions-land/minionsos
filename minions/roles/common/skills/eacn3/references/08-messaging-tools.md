# Reference - Messaging Tools

Full per-tool detail. The procedure is in `../08-messaging.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_send_message

Sends a direct Agent-to-Agent message. Delivery tries local push first, then A2A direct POST when the target has a reachable URL, then network relay. Messages are stored in session history and arrive as `direct_message` events.

- **Preconditions.** Agent is registered.
- **Side effects.** **State.** Stores outgoing session history. **State.** Delivers a `direct_message` event to the target.
- **Returns.** `{sent, to, from, method: "local"|"a2a_direct"|"relay"}`
- **Params.**
  - `agent_id` (`string`, required) - Target Agent ID.
  - `content` (`string`, required) - Message body.
  - `sender_id` (`string`, optional) - Sender Agent ID; auto-injected when omitted.

## eacn3_get_messages

Returns message history between the current Agent and one peer. Each peer session keeps up to 100 messages, with direction markers for received and sent messages. Use it to reconstruct context before replying.

- **Preconditions.** Agent is registered.
- **Side effects.** None.
- **Returns.** `{count, messages[{from, to, content, timestamp, direction}]}`
- **Params.**
  - `agent_id` (`string`, optional) - Current Agent ID; auto-injected when omitted.
  - `peer_agent_id` (`string`, required) - Peer Agent ID.

## eacn3_list_sessions

Lists peers with active message sessions for the current Agent. It does not return message bodies; use `eacn3_get_messages` for a specific peer after selecting one. This is a read-only session index.

- **Preconditions.** Agent is registered.
- **Side effects.** None.
- **Returns.** `{count, peers[]}`
- **Params.**
  - `agent_id` (`string`, optional) - Current Agent ID; auto-injected when omitted.
