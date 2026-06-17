import {AgentMarkdown} from './AgentMarkdown';

interface Props {
  text: string;
}

export function AgentProse({text}: Props) {
  return (
    <div className="agent-prose-text">
      <AgentMarkdown text={text} />
    </div>
  );
}
