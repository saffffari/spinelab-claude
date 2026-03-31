import { createHashRouter } from "react-router";
import LandingPage from "./pages/LandingPage";
import CaseViewer from "./pages/CaseViewer";
import MeasurementPage from "./pages/MeasurementPage";
import ReportPage from "./pages/ReportPage";

export const router = createHashRouter([
  {
    path: "/",
    Component: LandingPage,
  },
  {
    path: "/case/:patientId?",
    Component: CaseViewer,
  },
  {
    path: "/measurement/:patientId",
    Component: MeasurementPage,
  },
  {
    path: "/report/:patientId",
    Component: ReportPage,
  },
]);
