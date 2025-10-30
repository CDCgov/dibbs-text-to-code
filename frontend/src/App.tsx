import { Button, Card, CardBody, CardFooter, CardHeader, Textarea } from "@trussworks/react-uswds";
import { Layout } from "./components/Layout";


function App() {
  return (
    <Layout>
      <h1 className="font-merriweather font-bold lg:!text-5xl">Welcome to Text to Code!</h1>
      <p>The Text-to-Code project introduces a shared service integrated with the AIMS pipeline that can automatically map unstructured or local-coded fields in eICRs to standard codes (e.g. LOINC, SNOMED CT).</p>

      <h2>Convert your text for one code at a time</h2>
      <Card>
        <CardHeader>
          Nonstandard text input
        </CardHeader>
        <CardBody>
          <Textarea id={""} name={""}>

          </Textarea>
        </CardBody>
        <CardFooter>
          <Button type={"button"} children={undefined}>
            Submit
          </Button>
          <p>Note: Do not input PII/PHI</p>
        </CardFooter>
      </Card>
    </Layout>
  );
}

export default App;
