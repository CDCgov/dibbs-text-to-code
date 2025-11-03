import { Result } from "../../types";

interface ResultPanelProps {
  result: Result
}

export function DescriptionLine({ result }: ResultPanelProps) {
  return (
    <>
      <dt>{name}:</dt>
      <dd>{details}</dd>
    </>
  );
}
