/**
 * NOVA AI Assistant — Firebase Authentication Configuration & Helper Module
 * 
 * Provides:
 * - Firebase App & Auth initialization
 * - Google Sign-In Provider
 * - Email & Password Sign-Up with automated Email Verification
 * - Secure session management & persistence
 */

// Valid registered Firebase Web App Configuration
const firebaseConfig = {
  apiKey: "AIzaSyCO5PVg_yZF8VUnPn04wKtH8qLb2osnpbQ",
  authDomain: "nova-7c101.firebaseapp.com",
  projectId: "nova-7c101",
  storageBucket: "nova-7c101.firebasestorage.app",
  messagingSenderId: "338043817982",
  appId: "1:338043817982:web:7e802eb725507bb51b7aaf",
  measurementId: "G-CVJ8F91JBQ"
};

// Clean up any stale placeholder keys stored in localStorage from earlier runs
try {
  if (localStorage.getItem('nova_firebase_api_key')?.includes('DEMO')) {
    localStorage.removeItem('nova_firebase_api_key');
    localStorage.removeItem('nova_firebase_auth_domain');
    localStorage.removeItem('nova_firebase_project_id');
    localStorage.removeItem('nova_firebase_storage_bucket');
    localStorage.removeItem('nova_firebase_sender_id');
    localStorage.removeItem('nova_firebase_app_id');
  }
} catch (e) {
  // Ignore storage errors in restricted contexts
}

let firebaseApp = null;
let firebaseAuth = null;
let googleAuthProvider = null;

/**
 * Initialize Firebase Application and Authentication Service
 */
function initFirebase() {
  if (typeof firebase === 'undefined') {
    console.error('[NOVA-AUTH] Firebase SDK not loaded.');
    return null;
  }

  try {
    if (!firebase.apps.length) {
      firebaseApp = firebase.initializeApp(firebaseConfig);
    } else {
      firebaseApp = firebase.app();
    }

    firebaseAuth = firebase.auth();
    googleAuthProvider = new firebase.auth.GoogleAuthProvider();
    googleAuthProvider.setCustomParameters({ prompt: 'select_account' });

    // Set persistence to LOCAL (persists across browser restarts)
    firebaseAuth.setPersistence(firebase.auth.Auth.Persistence.LOCAL).catch(err => {
      console.warn('[NOVA-AUTH] Persistence setting warning:', err);
    });

    console.log('[NOVA-AUTH] Firebase Auth initialized successfully.');
    return firebaseAuth;
  } catch (err) {
    console.error('[NOVA-AUTH] Firebase initialization error:', err);
    return null;
  }
}

/**
 * Register with Email and Password, and send Email Verification link automatically
 */
async function registerWithEmail(email, password, displayName = '') {
  if (!firebaseAuth) initFirebase();
  try {
    const userCredential = await firebaseAuth.createUserWithEmailAndPassword(email, password);
    const user = userCredential.user;

    // Set display name if provided
    if (displayName && user.updateProfile) {
      await user.updateProfile({ displayName: displayName.trim() });
    }

    // Automatically send email verification link
    await user.sendEmailVerification({
      url: window.location.href,
      handleCodeInApp: false
    });

    console.log('[NOVA-AUTH] Verification email sent to:', email);
    return {
      success: true,
      user: user,
      emailSent: true,
      message: 'Verification email sent. Please check your inbox and verify your email.'
    };
  } catch (error) {
    console.error('[NOVA-AUTH] Registration error:', error);
    return {
      success: false,
      error: error,
      message: formatAuthErrorMessage(error)
    };
  }
}

/**
 * Sign In with Email and Password
 */
async function loginWithEmail(email, password) {
  if (!firebaseAuth) initFirebase();
  try {
    const userCredential = await firebaseAuth.signInWithEmailAndPassword(email, password);
    const user = userCredential.user;

    // Reload user to get latest emailVerified status
    await user.reload();

    return {
      success: true,
      user: firebaseAuth.currentUser,
      isVerified: firebaseAuth.currentUser.emailVerified
    };
  } catch (error) {
    console.error('[NOVA-AUTH] Email login error:', error);
    return {
      success: false,
      error: error,
      message: formatAuthErrorMessage(error)
    };
  }
}

/**
 * Sign In with Google Provider (Real Firebase Google Auth)
 */
async function loginWithGoogle() {
  if (!firebaseAuth) initFirebase();
  try {
    const result = await firebaseAuth.signInWithPopup(googleAuthProvider);
    const user = result.user;
    return {
      success: true,
      user: user,
      isVerified: true
    };
  } catch (error) {
    // Handle redirect fallback if popup is blocked on mobile
    if (error.code === 'auth/popup-blocked' || error.code === 'auth/popup-closed-by-user') {
      try {
        await firebaseAuth.signInWithRedirect(googleAuthProvider);
        return { success: true, redirecting: true };
      } catch (redirectErr) {
        return { success: false, error: redirectErr, message: formatAuthErrorMessage(redirectErr) };
      }
    }
    console.error('[NOVA-AUTH] Google login error:', error);
    return {
      success: false,
      error: error,
      message: formatAuthErrorMessage(error)
    };
  }
}

/**
 * Resend Email Verification Link
 */
async function resendVerificationEmail(user) {
  if (!user && firebaseAuth) user = firebaseAuth.currentUser;
  if (!user) {
    return { success: false, message: 'No authenticated user found.' };
  }
  try {
    await user.sendEmailVerification({
      url: window.location.href,
      handleCodeInApp: false
    });
    return {
      success: true,
      message: 'Verification email has been resent. Please check your inbox and spam folder.'
    };
  } catch (error) {
    console.error('[NOVA-AUTH] Resend verification error:', error);
    if (error.code === 'auth/too-many-requests') {
      return {
        success: false,
        message: 'Too many requests sent. Please wait a few minutes before trying again.'
      };
    }
    return {
      success: false,
      error: error,
      message: formatAuthErrorMessage(error)
    };
  }
}

/**
 * Check if current user's email has been verified
 */
async function checkEmailVerified() {
  if (!firebaseAuth) initFirebase();
  const user = firebaseAuth.currentUser;
  if (!user) return false;
  try {
    await user.reload();
    return firebaseAuth.currentUser.emailVerified;
  } catch (err) {
    console.warn('[NOVA-AUTH] Reload error:', err);
    return user.emailVerified;
  }
}

/**
 * Send Password Reset Email
 */
async function sendPasswordReset(email) {
  if (!firebaseAuth) initFirebase();
  try {
    await firebaseAuth.sendPasswordResetEmail(email, { url: window.location.href });
    return {
      success: true,
      message: 'Password reset link sent! Please check your email inbox.'
    };
  } catch (error) {
    console.error('[NOVA-AUTH] Password reset error:', error);
    return {
      success: false,
      error: error,
      message: formatAuthErrorMessage(error)
    };
  }
}

/**
 * Logout User
 */
async function logoutUser() {
  if (!firebaseAuth) initFirebase();
  try {
    await firebaseAuth.signOut();
    return { success: true };
  } catch (error) {
    console.error('[NOVA-AUTH] Sign out error:', error);
    return { success: false, error: error, message: formatAuthErrorMessage(error) };
  }
}

/**
 * User-friendly error message formatter
 */
function formatAuthErrorMessage(error) {
  if (!error) return 'An unknown error occurred.';
  const code = error.code || '';
  switch (code) {
    case 'auth/invalid-email':
      return 'The email address is not properly formatted.';
    case 'auth/user-disabled':
      return 'This user account has been disabled.';
    case 'auth/user-not-found':
      return 'No account found with this email. Please sign up.';
    case 'auth/wrong-password':
    case 'auth/invalid-credential':
      return 'Incorrect password or email. Please check and try again.';
    case 'auth/email-already-in-use':
      return 'An account already exists with this email address. Please sign in instead.';
    case 'auth/weak-password':
      return 'Password is too weak. Please use at least 6 characters.';
    case 'auth/operation-not-allowed':
      return 'Email/Password or Google sign-in is not enabled in the Firebase Console.';
    case 'auth/too-many-requests':
      return 'Too many unsuccessful attempts. Access temporarily disabled. Please try again later.';
    case 'auth/network-request-failed':
      return 'Network connection error. Please check your internet connection.';
    case 'auth/popup-closed-by-user':
      return 'Google sign-in was cancelled by closing the popup.';
    case 'auth/cancelled-popup-request':
      return 'Google sign-in popup was cancelled.';
    default:
      return error.message || 'Authentication failed. Please try again.';
  }
}

// Attach functions to window for global access across app.js
window.NovaAuth = {
  initFirebase,
  registerWithEmail,
  loginWithEmail,
  loginWithGoogle,
  resendVerificationEmail,
  checkEmailVerified,
  sendPasswordReset,
  logoutUser,
  getAuth: () => firebaseAuth || initFirebase()
};
