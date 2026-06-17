import type {ActionChoice} from '../types';

/**
 * Renders clickable buttons for an action_choices artifact, so the user can
 * pick one of the agent's options without typing. Clicking sends the option's
 * value (or its label) back to the agent as a normal user message.
 */
export const ActionChoicesCard = ({
  options,
  onChoose,
  disabled,
}: {
  options: ActionChoice[];
  onChoose: (text: string) => void;
  disabled?: boolean;
}) => {
  return (
    <div className="action-choices">
      {options.map((opt, i) => (
        <button
          key={`${opt.label}-${i}`}
          type="button"
          className="action-choice"
          disabled={disabled}
          onClick={() => onChoose(opt.value ?? opt.label)}>
          <span className="action-choice-index">{i + 1}</span>
          <span className="action-choice-label">{opt.label}</span>
        </button>
      ))}
    </div>
  );
};
