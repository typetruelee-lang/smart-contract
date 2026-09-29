import { Component, type ReactNode, lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ErrorView, Loading, Page, ToastProvider } from "./components/ui";
import { AuthProvider, RequireAuth } from "./lib/auth";
import Home from "./pages/Home";
import Login from "./pages/Login";

const CreateMenu = lazy(() => import("./pages/CreateMenu"));
const TextEditor = lazy(() => import("./pages/TextEditor"));
const TemplatePick = lazy(() => import("./pages/TemplatePick"));
const PdfEditor = lazy(() => import("./pages/PdfEditor"));
const ContractPage = lazy(() => import("./pages/ContractPage"));
const SignFlow = lazy(() => import("./pages/SignFlow"));
const Complete = lazy(() => import("./pages/Complete"));
const Invite = lazy(() => import("./pages/Invite"));
const MyContracts = lazy(() => import("./pages/MyContracts"));
const Verify = lazy(() => import("./pages/Verify"));
const Admin = lazy(() => import("./pages/Admin"));
const Evidence = lazy(() => import("./pages/Evidence"));

class Boundary extends Component<{ children: ReactNode }, { err: Error | null }> {
  state = { err: null as Error | null };
  static getDerivedStateFromError(err: Error) {
    return { err };
  }
  render() {
    if (this.state.err)
      return (
        <Page title="" back={false}>
          <ErrorView message="화면을 표시하지 못했어요. 새로고침해 주세요." onRetry={() => window.location.reload()} />
        </Page>
      );
    return this.props.children;
  }
}

const auth = (el: ReactNode) => <RequireAuth>{el}</RequireAuth>;

export default function App() {
  return (
    <Boundary>
      <ToastProvider>
        <AuthProvider>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/login" element={<Login />} />
              <Route path="/create" element={auth(<CreateMenu />)} />
              <Route path="/create/text" element={auth(<TextEditor />)} />
              <Route path="/create/template" element={auth(<TemplatePick />)} />
              <Route path="/create/pdf" element={auth(<PdfEditor />)} />
              <Route path="/contracts" element={auth(<MyContracts />)} />
              <Route path="/contracts/:id" element={auth(<ContractPage />)} />
              <Route path="/contracts/:id/edit" element={auth(<TextEditor />)} />
              <Route path="/contracts/:id/sign" element={auth(<SignFlow />)} />
              <Route path="/contracts/:id/done" element={auth(<Complete />)} />
              <Route path="/contracts/:id/evidence" element={auth(<Evidence />)} />
              <Route path="/invite/:token" element={auth(<Invite />)} />
              <Route path="/verify" element={<Verify />} />
              <Route path="/verify/:vid" element={<Verify />} />
              <Route path="/admin" element={<Admin />} />
              <Route
                path="*"
                element={
                  <Page title="">
                    <ErrorView message="찾으시는 화면이 없어요." />
                  </Page>
                }
              />
            </Routes>
          </Suspense>
        </AuthProvider>
      </ToastProvider>
    </Boundary>
  );
}
