# One frozen river, judged four ways

This run asks one question: on one identical state, do persona criteria change the action, and does the bluff judgment change the next call.

## The spot

Hand 2, river. The logged hole cards are 2h 2c. The board is Ks As Jd 4s 5d. The pot is 320. The legal actions are check, raise_half_pot, raise_pot, and all_in.

The logged equity against the continuing range is 0.08333333333333333. The logged equity against a random hand is 0.32666666666666666. That equity is Monte Carlo. Pot odds are 0.0, with 0 to call. Stack-to-pot is 5.84375, from a stack of 1870 behind the pot of 320.

The four votes reused that logged state. They did not deal a new hand.

## The loop

Call A asks only bluff_spot and range_advantage. It does not ask for an action. bluff_spot is a noul. range_advantage is a score. Those two values are copied onto prior_judgments for the next call: bluff_spot keeps the noul, range_advantage_score keeps the score, and range_advantage_label is the label below.

The label rule rounds the score to an integer, clamps that integer to the range 0 through 4, and reads this list:

| Rounded score | Label |
| --- | --- |
| 0 | Clear disadvantage |
| 1 | Slight disadvantage |
| 2 | Neutral |
| 3 | Slight advantage |
| 4 | Clear advantage |

The vote-file scores map as follows. Rock 0.67 rounds to 1, Slight disadvantage. Shark 0.69 rounds to 1, Slight disadvantage. Caller 0.78 rounds to 1, Slight disadvantage. Maniac 0.7 rounds to 1, Slight disadvantage.

Call B asks only the action. Its criteria are the logged legal actions: check, raise_half_pot, raise_pot, and all_in. prior_judgments are evidence for that choice, not orders.

The equity rule is math_action. It is computed in code from the logged state, and no Jev action is passed into it. It is not a Jev action.

## The four votes

| Persona | Action | Confidence | Check | Raise half pot | Raise pot | All in | Bluff | Range score | Range label | math_action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Rock | check | 0.93 | 0.95 | 0.03 | 0.01 | 0.01 | 0.22 | 0.67 | Slight disadvantage | check |
| Shark | check | 0.61 | 0.71 | 0.25 | 0.02 | 0.02 | 0.2 | 0.69 | Slight disadvantage | check |
| Caller | check | 0.84 | 0.88 | 0.08 | 0.03 | 0.01 | 0.24 | 0.78 | Slight disadvantage | check |
| Maniac | raise_half_pot | 0.2 | 0.22 | 0.4 | 0.2 | 0.18 | 0.44 | 0.7 | Slight disadvantage | check |

The range scores are the shared part: 0.67, 0.69, 0.78, and 0.7, all Slight disadvantage. The action and the bluff score are the split. Rock, Shark, and Caller play check, with bluff scores 0.22, 0.2, and 0.24. Maniac plays raise_half_pot, with bluff score 0.44. math_action is check on every row.

The hand log of this same decision has a different Maniac distribution: check 0.32, raise_half_pot 0.38, raise_pot 0.17, all_in 0.13. The vote file has check 0.22, raise_half_pot 0.4, raise_pot 0.2, all_in 0.18. The vote file is a second sample of the same state. The two samples stay separate. In the hand log the played action is also raise_half_pot, at confidence 0.17, with bluff 0.41 and range score 0.6. That logged score rounds to 1, Slight disadvantage. The logged math_action is check.

## The bluff control

The two extra calls are Maniac only. They keep the range judgment from Maniac's own call A in the vote file: range score 0.7, Slight disadvantage. They do not ask bluff_spot or range_advantage again. bluff_spot is forced to 0.1 on one call and to 0.9 on the other. Each call asks only the action, over the same four legal actions.

| bluff_spot | Action | Confidence | Check | Raise half pot | Raise pot | All in |
| --- | --- | --- | --- | --- | --- | --- |
| 0.1 | check | 0.59 | 0.69 | 0.15 | 0.09 | 0.07 |
| 0.9 | raise_half_pot | 0.19 | 0.02 | 0.39 | 0.3 | 0.29 |

The move from 0.1 to 0.9 changes the played action from check to raise_half_pot. Check goes from 0.69 to 0.02. Raise half pot goes from 0.15 to 0.39. Raise pot goes from 0.09 to 0.3. All in goes from 0.07 to 0.29. Confidence goes from 0.59 to 0.19. The range score stays 0.7.

## Model reading

On this spot Jev is used as a component with four visible parts.

The action set is closed. Call B can answer only with check, raise_half_pot, raise_pot, or all_in, the legal actions stored on the logged state.

The answer is a distribution rather than a sentence. Each action call returns a probability on those four actions, plus a confidence on the played choice.

A side judgment is available to the next call. Call A produces bluff_spot and range_advantage, and those values are copied onto prior_judgments before the action call. The forced rows show the same slot in use: the range score stays 0.7, and only bluff_spot changes.

A formula sits beside the choice. math_action is computed in code and returns check for all four personas. Maniac's played action in the vote file is raise_half_pot, so the formula and the played action stand on different rows of the same state.

On the forced 0.9 call the raise mass is spread across sizes: raise_half_pot 0.39, raise_pot 0.3, and all_in 0.29, with check at 0.02. Confidence on that call is 0.19.

Shark's own distribution keeps a residual on the raise. Shark plays check at 0.71 and still assigns 0.25 to raise_half_pot. Rock assigns 0.03 to raise_half_pot, and Caller assigns 0.08.

## Limits

This file is one river. It is four criteria on one state, plus two forced bluff values, 0.1 and 0.9. Personas differ by criteria text. The state those criteria read is the copied log, not a new deal. This file does not support a win rate, a ranking against any other model, or a claim that the action was good poker.

## Blog spine

One copied river, 2h 2c on Ks As Jd 4s 5d, splits the action: Rock, Shark, and Caller check, and Maniac raises half the pot. The four range scores, 0.67, 0.69, 0.78, and 0.7, all map to Slight disadvantage, while the bluff scores split from 0.2, 0.22, and 0.24 on the checks to 0.44 on the raise. With Maniac's range score held at 0.7, forcing bluff_spot from 0.1 to 0.9 moves the next call from check to raise_half_pot, and check moves from 0.69 to 0.02. At bluff_spot 0.9 the raise probability is spread across half pot 0.39, pot 0.3, and all in 0.29, with confidence 0.19. The hand log and the vote file are two samples of this state, and the file supports neither a win rate nor a ranking.
