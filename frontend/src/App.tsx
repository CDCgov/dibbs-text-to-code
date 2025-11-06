import {
  Button,
  ButtonGroup,
  CharacterCount,
  Icon,
} from '@trussworks/react-uswds';
import { Layout } from './components/Layout';
import { useState } from 'react';
import { Title } from './components/Title';
import { Panel } from './components/Panel';
import { DescriptionLine } from './components/DescriptionLine';
import { Coding, Result } from './types';

function App() {
  const [textInput, setTextInput] = useState('');
  const maxInputLength = 200;
  const [result, setResult] = useState<Result>();
  const [currentCoding, setCurrentCoding] = useState<Coding | undefined>();

  const handleChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setTextInput(event.target.value);
  };

  const handleSubmit = async () => {
    try {
      const response = await fetch(
        'http://localhost:8080/api/process/' + textInput,
        {
          method: 'GET',
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data: Result = await response.json();
      setResult(data);
      setCurrentCoding(data.codings[0]);
    } catch (err) {
      console.log(err);
    }
  };
  const handleSubmitBad = async () => {
    try {
      const response = await fetch(
        'http://localhost:8080/api/process/' + textInput + '?is_bad=true',
        {
          method: 'GET',
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log(data);
      setResult(data);
    } catch (err) {
      console.log(err);
    }
  };

  return (
    <Layout>
      <div className="flex justify-center">
        <div className="max-w-7xl">
          <Title className="pt-10">Welcome to Text to Code!</Title>
          <p className="mt-2">
            The Text-to-Code project introduces a shared service integrated with
            the AIMS pipeline that can automatically map unstructured or
            local-coded fields in eICRs to standard codes (e.g. LOINC, SNOMED
            CT).
          </p>
          <h2 className="mt-10">Convert your text for one code at a time</h2>
          <div className="flex gap-8">
            <Panel title="Nonstandard text input">
              <CharacterCount
                className="bg-gray-100"
                id="text-input"
                name="text-input"
                placeholder="Measles genotype A probe"
                maxLength={maxInputLength}
                value={textInput}
                onChange={handleChange}
                required
                isTextArea
              />
              <div className="mt-4 flex">
                <ButtonGroup type="segmented">
                  <Button type="button" onClick={handleSubmit}>
                    Submit <span className='text-xs'>(match)</span>
                  </Button>
                  <Button type="button" onClick={handleSubmitBad}>
                    Submit <span className='text-xs'>(no match)</span>
                  </Button>
                </ButtonGroup>
                <strong className="ml-4 font-light!" role="note">
                  Note: Do not input PII/PHI
                </strong>
              </div>
            </Panel>

            {currentCoding ? (
              <Panel
                title="Standardized output"
                header={
                  result?.codings && result.codings.length > 1 ? (
                    <Button
                      type="button"
                      unstyled
                      onClick={() => setCurrentCoding(undefined)}
                    >
                      Back to all similar codes
                    </Button>
                  ) : (
                    ''
                  )
                }
              >
                <span className="font-extralight">
                  {currentCoding.shortName}
                </span>
                <dl className="outline-gray-cool-10 mt-6 mb-4 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-4 outline">
                  <DescriptionLine name="Code" details={currentCoding.code} />
                  <DescriptionLine
                    name="Code System"
                    details={currentCoding.codeSystem}
                  />
                  <DescriptionLine
                    name="Display Name"
                    details={currentCoding.longName}
                  />
                </dl>
                <Button type="button" outline>
                  <Icon.ContentCopy /> Copy
                </Button>
              </Panel>
            ) : result?.codings.length && result.codings.length > 1 ? (
              <Panel
                title="We were unable to find a matching code for this text."
                warning
              >
                <p>Closest matches:</p>
                <ul className="ml-6 list-disc">
                  {result.codings.map((coding) => (
                    <li>
                      <Button
                        type="button"
                        className="leading-6"
                        unstyled
                        onClick={() => setCurrentCoding(coding)}
                      >
                        {coding.shortName}
                      </Button>
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : (
              ''
            )}
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default App;
