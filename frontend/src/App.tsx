import {
  Button,
  CharacterCount,
  Form,
  FormGroup,
  Icon,
  Label,
} from '@trussworks/react-uswds';
import { Layout } from './components/Layout';
import { useState } from 'react';
import { Title } from './components/Title';

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
        <div className="max-w-320">
          <Title className="pt-10">Welcome to Text to Code!</Title>
          <p className="mt-2">
            The Text-to-Code project introduces a shared service integrated with
            the AIMS pipeline that can automatically map unstructured or
            local-coded fields in eICRs to standard codes (e.g. LOINC, SNOMED
            CT).
          </p>
          <h2 className="mt-10">Convert your text for one code at a time</h2>
          <div className="flex gap-8">
            <div className="bg-blue-cool-5 mt-4 max-w-100 rounded-lg p-8">
              <Label htmlFor="text-input">
                <span className="text-lg font-bold">
                  Nonstandard text input
                </span>
              </Label>
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
                ></CharacterCount>
              </div>
              <div className="mt-4">
                <Button type="button" id="fetchDataBtn" onClick={handleSubmit}>
                  Submit
                </Button>
                <strong className="ml-4 font-light!" role="note">
                  Note: Do not input PII/PHI
                </strong>
              </div>
            </div>

            {result ? (
              <div className="bg-blue-cool-5 mt-4 max-w-100 max-w-full rounded-lg p-8">
                <h3 className="text-lg font-bold">Standardized output</h3>
                <span className="font-extralight">{result.input}</span>
                <dl className="outline-gray-cool-10 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 p-4 outline">
                  <dt>Code:</dt>
                  <dd>{result.code}</dd>
                  <dt>Code system:</dt>
                  <dd>{result.codeSystem}</dd>
                  <dt>Display name:</dt>
                  <dd>{result.displayName}</dd>
                </dl>
                <button>
                  <Icon.ContentCopy /> Copy
                </button>
              </div>
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
