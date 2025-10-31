import {
  Button,
  CharacterCount,
  Icon,
} from '@trussworks/react-uswds';
import { Layout } from './components/Layout';
import { useState } from 'react';
import { Title } from './components/Title';
import { Panel } from './components/Panel';
import { DescriptionLine } from './components/DescriptionLine';

interface Result {
  input: string;
  code: string;
  codeSystem: string;
  displayName: string;
}

function App() {
  const [textInput, setTextInput] = useState('');
  const maxInputLength = 200;
  const [result, setResult] = useState<Result>();

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

      const data = await response.json();
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
              <div>
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
              </div>
              <div className="mt-4">
                <Button type="button" id="fetchDataBtn" onClick={handleSubmit}>
                  Submit
                </Button>
                <strong className="ml-4 font-light!" role="note">
                  Note: Do not input PII/PHI
                </strong>
              </div>
            </Panel>

            {result ? (
              <Panel title="Standardized output">
                <span className="font-extralight">{result.input}</span>
                <dl className="outline-gray-cool-10 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-4 outline mt-6 mb-4">
                  <DescriptionLine name="Code" details={result.code} />
                  <DescriptionLine name="Code System" details={result.codeSystem} />
                  <DescriptionLine name="Display Name" details={result.displayName} />
                </dl>
                <Button type={'button'} outline>
                  <Icon.ContentCopy /> Copy
                </Button>
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
