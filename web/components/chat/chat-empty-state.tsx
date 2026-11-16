import { FileText, Network, Search } from "lucide-react";
import { usePromptInputController } from "@/components/ai-elements/prompt-input";
import { cn } from "@/lib/utils";

// Original mark: a central document node with three evidence satellites -
// no imagery borrowed from any reference design, just currentColor so it
// follows the existing theme (no new palette entries).
export function EvidenceMark({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
      className={cn("size-14 text-muted-foreground", className)}
    >
      <path
        d="M32 18v10M17 38l10.5-9M47 38l-10.5-9M32 28v22"
        stroke="currentColor"
        strokeWidth="1.3"
        opacity="0.55"
      />
      <circle cx="32" cy="14" r="3.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="14" cy="40" r="3.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="50" cy="40" r="3.5" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="32" cy="55" r="2.5" fill="currentColor" />
      <circle cx="32" cy="28" r="6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export function ChatGreeting({ name }: { name: string }) {
  return (
    <div className="flex flex-col items-center gap-2 text-center">
      <p className="text-sm font-medium text-muted-foreground">Welcome back, {name}</p>
      <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
        What would you like to explore?
      </h1>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
        Ask questions, explore your documents, and discover evidence-backed answers.
      </p>
    </div>
  );
}

const SUGGESTIONS = [
  {
    icon: FileText,
    title: "Summarize Documents",
    description: "Get a concise overview of your uploaded sources.",
    prompt: "Summarize the key findings across all my uploaded documents.",
  },
  {
    icon: Search,
    title: "Find Supporting Evidence",
    description: "Discover passages that support a specific claim.",
    prompt: "Find passages that support the claim that ",
  },
  {
    icon: Network,
    title: "Explore Connections",
    description: "Identify relationships across your knowledge base.",
    prompt: "What connections exist between the entities discussed across my documents?",
  },
] as const;

// Must render inside a PromptInputProvider - prefills the shared textInput
// state (see ai-elements/prompt-input.tsx's controller) on a card click
// without threading a ref through the form.
export function ComposerSuggestions() {
  const { textInput } = usePromptInputController();
  return <SuggestionCards onSelect={textInput.setInput} />;
}

function SuggestionCards({ onSelect }: { onSelect: (prompt: string) => void }) {
  return (
    <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-3">
      {SUGGESTIONS.map(({ icon: Icon, title, description, prompt }) => (
        <button
          key={title}
          type="button"
          onClick={() => onSelect(prompt)}
          className="flex flex-col gap-2 rounded-xl border border-border bg-card/40 p-3.5 text-left transition-colors hover:border-input hover:bg-accent"
        >
          <Icon className="size-4 text-muted-foreground" />
          <span className="text-xs font-semibold text-foreground">{title}</span>
          <span className="text-xs leading-relaxed text-muted-foreground">{description}</span>
        </button>
      ))}
    </div>
  );
}
