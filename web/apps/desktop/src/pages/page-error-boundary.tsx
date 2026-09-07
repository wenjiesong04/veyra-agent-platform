import * as React from "react";

type PageErrorBoundaryProps = {
  resetKey: string;
  locale: "zh" | "en";
  children: React.ReactNode;
};

type PageErrorBoundaryState = {
  error: Error | null;
};

export class PageErrorBoundary extends React.Component<PageErrorBoundaryProps, PageErrorBoundaryState> {
  state: PageErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): PageErrorBoundaryState {
    return { error };
  }

  componentDidUpdate(prevProps: PageErrorBoundaryProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    const error = this.state.error;
    if (!error) return this.props.children;
    const zh = this.props.locale === "zh";
    return (
      <div className="page-stack">
        <div className="studio-alert bad" role="alert">
          <div>{zh ? "这个页面渲染失败，工作区还在。可以重试，或从左侧再打开一次。" : "This page failed to render. The workspace is still here. Retry, or open the item again from the sidebar."}</div>
          <div>{error.message}</div>
          <button type="button" onClick={() => this.setState({ error: null })}>{zh ? "重试" : "Retry"}</button>
        </div>
      </div>
    );
  }
}
