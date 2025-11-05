interface DescriptionLineProps {
  name: string;
  details: string;
}

export function DescriptionLine({ name, details }: DescriptionLineProps) {
  return (
    <>
      <dt>{name}:</dt>
      <dd>{details}</dd>
    </>
  );
}
