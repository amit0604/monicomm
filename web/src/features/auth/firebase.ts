// DEV-ONLY. Loaded on demand by the login page, never part of a production build.
import { initializeApp } from "firebase/app";
import {
  getAuth,
  GoogleAuthProvider,
  inMemoryPersistence,
  setPersistence,
  signInWithEmailAndPassword,
  signInWithPopup,
  signOut,
} from "firebase/auth";

export interface FirebaseSettings {
  api_key: string;
  auth_domain: string;
  project_id: string;
  admin_login: string;
}

export function createSignIn(settings: FirebaseSettings) {
  const auth = getAuth(
    initializeApp({
      apiKey: settings.api_key,
      authDomain: settings.auth_domain,
      projectId: settings.project_id,
    }),
  );
  // The api keeps the session in its own cookie, so nothing is left in browser storage.
  const ready = setPersistence(auth, inMemoryPersistence);
  const token = async (signIn: () => ReturnType<typeof signInWithPopup>) => {
    const { user } = await signIn();
    const idToken = await user.getIdToken();
    await signOut(auth);
    return idToken;
  };
  return {
    google: () => token(() => signInWithPopup(auth, new GoogleAuthProvider())),
    password: async (email: string, password: string) => {
      await ready;
      return token(() => signInWithEmailAndPassword(auth, email, password));
    },
  };
}
export type SignIn = ReturnType<typeof createSignIn>;
