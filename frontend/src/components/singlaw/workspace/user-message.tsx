import { FileText } from "lucide-react";
import { Message, MessageContent } from "@/components/ai-elements/message";
import type { UiMessage } from "@/lib/singlaw";

export function UserMessage({ message }: { message: UiMessage }) {
  return (
    <Message from="user" className="singlaw-message">
      <MessageContent data-user-content="">
        {message.attachments && message.attachments.length > 0 && (
          <ul className="message-attachments" aria-label="Attached documents">
            {message.attachments.map((a) => (
              <li key={a.id} className="attachment-chip">
                <FileText size={12} aria-hidden="true" />
                <span className="truncate max-w-48">{a.filename}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="user-text">{message.text}</p>
      </MessageContent>
    </Message>
  );
}
