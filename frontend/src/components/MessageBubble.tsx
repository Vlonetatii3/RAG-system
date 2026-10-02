import { format } from 'date-fns';
import Markdown from './Markdown';
import type { Message } from '../types';

interface Props {
  message: Message;
  active?: boolean;
  onShowSources?: () => void;
}

export default function MessageBubble({ message, active, onShowSources }: Props) {
  const isUser = message.role === 'user';
  const sourceCount = message.sources?.length ?? 0;

  return (
    <div className={`message message--${message.role} ${message.isError ? 'message--error' : ''}`}>
      <div className="bubble">{isUser ? <p>{message.content}</p> : <Markdown>{message.content}</Markdown>}</div>
      <div className="message-meta">
        <time dateTime={message.createdAt}>{format(new Date(message.createdAt), 'HH:mm')}</time>
        {!isUser && sourceCount > 0 && (
          <button className={`link-btn ${active ? 'link-btn--active' : ''}`} onClick={onShowSources}>
            {sourceCount} fuente{sourceCount > 1 ? 's' : ''}
          </button>
        )}
      </div>
    </div>
  );
}
