"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { toast } from "sonner";
import type { User } from "@supabase/supabase-js";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { avatarUrl, cn } from "@/lib/utils";
import { signOut } from "@/lib/auth";
import { supabase } from "@/lib/supabase";
import { User as UserIcon, CircleUser } from "lucide-react";

type ProfileMetadata = {
  full_name?: string;
  profession?: string;
  bio?: string;
  avatar_seed?: string;
};

const SECTIONS = [
  { id: "profile", label: "Profile", icon: UserIcon },
  { id: "account", label: "Account", icon: CircleUser },
] as const;

type SectionId = (typeof SECTIONS)[number]["id"];

function displayName(email: string | undefined, fullName: string | undefined): string {
  if (fullName) return fullName;
  if (!email) return "Account";
  return email.split("@")[0];
}

// Keyed by user.id by the caller so this remounts (and re-reads initial
// metadata) if the signed-in user ever changes, instead of syncing local
// form state from a prop via an effect.
function ProfileSection({ user }: { user: User }) {
  const metadata = user.user_metadata as ProfileMetadata | undefined;
  const [fullName, setFullName] = useState(metadata?.full_name ?? "");
  const [profession, setProfession] = useState(metadata?.profession ?? "");
  const [bio, setBio] = useState(metadata?.bio ?? "");
  const [avatarSeed, setAvatarSeed] = useState(metadata?.avatar_seed);
  const [isSaving, setIsSaving] = useState(false);
  const [isShuffling, setIsShuffling] = useState(false);

  const name = displayName(user.email, fullName);
  const seed = avatarSeed ?? fullName ?? user.email;

  async function handleSaveProfile(event: FormEvent) {
    event.preventDefault();
    setIsSaving(true);
    try {
      const { error } = await supabase.auth.updateUser({
        data: { full_name: fullName.trim(), profession: profession.trim(), bio: bio.trim() },
      });
      if (error) throw error;
      toast.success("Profile updated.");
    } catch {
      toast.error("Couldn't update your profile.");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleShuffleAvatar() {
    setIsShuffling(true);
    const newSeed = crypto.randomUUID();
    try {
      const { error } = await supabase.auth.updateUser({ data: { avatar_seed: newSeed } });
      if (error) throw error;
      setAvatarSeed(newSeed);
    } catch {
      toast.error("Couldn't shuffle the avatar.");
    } finally {
      setIsShuffling(false);
    }
  }

  async function handleResetAvatar() {
    setIsShuffling(true);
    try {
      const { error } = await supabase.auth.updateUser({ data: { avatar_seed: null } });
      if (error) throw error;
      setAvatarSeed(undefined);
    } catch {
      toast.error("Couldn't reset the avatar.");
    } finally {
      setIsShuffling(false);
    }
  }

  return (
    <form onSubmit={handleSaveProfile} className="flex flex-col gap-6">
      <h2 className="text-sm font-semibold text-foreground">Profile</h2>

      <div className="flex items-center gap-4">
        <Avatar className="size-14">
          <AvatarImage src={avatarUrl(seed)} alt={name} />
          <AvatarFallback>{name.charAt(0).toUpperCase()}</AvatarFallback>
        </Avatar>
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" onClick={handleShuffleAvatar} disabled={isShuffling}>
            Shuffle avatar
          </Button>
          {avatarSeed && (
            <Button type="button" variant="ghost" size="sm" onClick={handleResetAvatar} disabled={isShuffling}>
              Reset
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="settings-full-name">Full name</Label>
          <Input id="settings-full-name" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Your name" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="settings-profession">Profession</Label>
          <Input
            id="settings-profession"
            value={profession}
            onChange={(e) => setProfession(e.target.value)}
            placeholder="e.g. UI/UX Designer"
          />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="settings-bio">Bio</Label>
        <Textarea id="settings-bio" value={bio} onChange={(e) => setBio(e.target.value)} placeholder="A short bio" rows={3} />
      </div>

      <Button type="submit" disabled={isSaving} className="self-start">
        {isSaving ? "Saving…" : "Save changes"}
      </Button>
    </form>
  );
}

function AccountSection({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-sm font-semibold text-foreground">Account</h2>

      <div className="flex flex-col gap-1.5">
        <Label>Email</Label>
        <Input value={user.email ?? ""} disabled />
      </div>

      {user.created_at && (
        <div className="flex flex-col gap-1.5">
          <Label>Member since</Label>
          <p className="text-sm text-muted-foreground">
            {new Date(user.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </p>
        </div>
      )}

      <Separator />

      <Button type="button" variant="destructive" className="self-start" onClick={onSignOut}>
        Log out
      </Button>
    </div>
  );
}

export function SettingsDialog({
  open,
  onOpenChange,
  user,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null | undefined;
}) {
  const [activeSection, setActiveSection] = useState<SectionId>("profile");

  if (!user) return null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (next) setActiveSection("profile");
      }}
    >
      <DialogContent className="flex h-[28rem] max-w-2xl flex-row gap-0 overflow-hidden p-0 sm:max-w-2xl">
        <DialogTitle className="sr-only">Settings</DialogTitle>

        <aside className="flex w-44 shrink-0 flex-col gap-0.5 border-r border-border bg-muted/30 p-3">
          <p className="mb-2 px-2.5 text-xs font-medium text-muted-foreground">Settings</p>
          {SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => setActiveSection(section.id)}
              className={cn(
                "flex items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-sm transition-colors [&_svg]:size-4",
                activeSection === section.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )}
            >
              <section.icon />
              {section.label}
            </button>
          ))}
        </aside>

        <div className="flex-1 overflow-y-auto p-6">
          {activeSection === "profile" && <ProfileSection key={user.id} user={user} />}
          {activeSection === "account" && (
            <AccountSection user={user} onSignOut={() => signOut().then(() => onOpenChange(false))} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
