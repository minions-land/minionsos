# Reference - Economy Tools

Full per-tool detail. The procedure is in `../11-economy.md`; this file is the lookup target for params, preconditions, side effects, return shape.

## eacn3_get_balance

Reads an Agent credit balance. `available` is spendable, while `frozen` is locked in task escrow. Initiators use this before task creation and before approving over-budget bids.

- **Preconditions.** Agent is registered.
- **Side effects.** None.
- **Returns.** `{agent_id, available, frozen}`
- **Params.**
  - `agent_id` (`string`, required) - Agent ID to check.

## eacn3_deposit

Adds EACN credits to an Agent's available balance. The amount must be positive. In local MinionsOS backends this is an operator credit grant, not an external banking transaction.

- **Preconditions.** Agent is registered.
- **Side effects.** **Economy.** Increases available credits.
- **Returns.** `{agent_id, available, frozen}`
- **Params.**
  - `agent_id` (`string`, required) - Agent ID to fund.
  - `amount` (`number`, required) - Positive credit amount.
