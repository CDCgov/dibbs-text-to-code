import { Button, FormGroup, Label, Textarea } from "@trussworks/react-uswds";
import { Layout } from "./components/Layout";


function App() {
  return (
    <Layout>
      <div className="flex justify-center">
        <div className="max-w-[1280px]">
          <h1 className="font-merriweather font-bold lg">Welcome to Text to Code!</h1>
          <p>The Text-to-Code project introduces a shared service integrated with the AIMS pipeline that can automatically map unstructured or local-coded fields in eICRs to standard codes (e.g. LOINC, SNOMED CT).</p>
          <h2>Convert your text for one code at a time</h2>
          <div className="bg-blue-cool-5 max-w-[400px] rounded-lg p-4">
            <FormGroup>
              <Label htmlFor="text-input">
                Nonstandard text input
              </Label>
              <Textarea
                className="bg-gray-100"
                id="text-input"
                name="text-input"
                placeholder="Measles genotype A probe"
                maxLength={200}>
              </Textarea>
              <Button type={"button"}>
                Submit
              </Button>
              <strong className="!font-normal">Note: Do not input PII/PHI</strong>
            </FormGroup>
          </div>
        </div>
      </div>
    </Layout>
  );
}

export default App;
