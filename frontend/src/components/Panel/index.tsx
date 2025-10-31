interface PanelProps {
  children: React.ReactNode;
  title: string
}

export function Panel({ children, title }: PanelProps) {
  return (
    <div className="bg-blue-cool-5 mt-4 max-w-full rounded-lg p-8 max-h-max">
      <h3 className="text-lg font-bold">
        {title}
      </h3>
      {children}
    </div>
  )
}
