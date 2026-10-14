"use client";

import { Component, type ReactNode } from "react";

import { CrashCard } from "@/components/common/CrashCard";

/** Keeps one widget's crash (map, timeline) from taking the whole screen down. */
export class SafeBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) return <CrashCard compact error={this.state.error} retry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
