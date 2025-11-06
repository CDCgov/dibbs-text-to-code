interface PanelProps {
  header?: React.ReactNode;
  children: React.ReactNode;
  title: string;
  warning?: boolean;
}

export function Panel({ header, children, title, warning }: PanelProps) {
  let panelTitleStyle = 'text-lg font-bold';
  if (warning) {
    panelTitleStyle += ' text-state-error-dark';
  }

  return (
    <>
      <div className="bg-blue-cool-5 mt-4 max-w-full rounded-lg p-8">
        <div>{header}</div>
        <h3 className={panelTitleStyle}>{title}</h3>
        <div className="pt-4">{children}</div>
      </div>
    </>
  );
}
