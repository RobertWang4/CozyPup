import { useState, useEffect } from 'react';
import { X, Bell, Pill, BarChart3, Shield, FileText, Info, LogOut, ChevronRight, Plus, Dog, Cat, Trash2, ArrowLeft } from 'lucide-react';
import { hapticMedium } from '../utils/haptics';
import styles from './SettingsDrawer.module.css';
import { usePets, petStore } from '../stores/petStore';
import { useAuth, authStore } from '../stores/authStore';
import PetForm from './PetForm';
import type { Pet } from '../types/pets';

type SubPage = null | 'privacy' | 'disclaimer' | 'about';

const NOTIF_PREFS_KEY = 'cozypup_notification_prefs';

interface NotificationPrefs {
  notifications: boolean;
  medication: boolean;
  insights: boolean;
}

function loadNotificationPrefs(): NotificationPrefs {
  try {
    const stored = localStorage.getItem(NOTIF_PREFS_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        notifications: parsed.notifications ?? true,
        medication: parsed.medication ?? true,
        insights: parsed.insights ?? true,
      };
    }
  } catch {
    // ignore parse errors
  }
  return { notifications: true, medication: true, insights: true };
}

function saveNotificationPrefs(prefs: NotificationPrefs) {
  localStorage.setItem(NOTIF_PREFS_KEY, JSON.stringify(prefs));
}

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const [notifications, setNotifications] = useState(true);
  const [medication, setMedication] = useState(true);
  const [insights, setInsights] = useState(true);
  const [subPage, setSubPage] = useState<SubPage>(null);

  // Load notification prefs from localStorage on mount
  useEffect(() => {
    const prefs = loadNotificationPrefs();
    setNotifications(prefs.notifications);
    setMedication(prefs.medication);
    setInsights(prefs.insights);
  }, []);

  function handleToggleNotifications() {
    const next = !notifications;
    setNotifications(next);
    saveNotificationPrefs({ notifications: next, medication, insights });
  }

  function handleToggleMedication() {
    const next = !medication;
    setMedication(next);
    saveNotificationPrefs({ notifications, medication: next, insights });
  }

  function handleToggleInsights() {
    const next = !insights;
    setInsights(next);
    saveNotificationPrefs({ notifications, medication, insights: next });
  }

  const [showPetForm, setShowPetForm] = useState(false);
  const [editingPet, setEditingPet] = useState<Pet | null>(null);

  const pets = usePets();
  const auth = useAuth();

  function handleAddPet() {
    setEditingPet(null);
    setShowPetForm(true);
  }

  function handleEditPet(pet: Pet) {
    setEditingPet(pet);
    setShowPetForm(true);
  }

  function handleSavePet(data: Omit<Pet, 'id' | 'avatarUrl' | 'color' | 'createdAt'>) {
    if (editingPet) {
      petStore.update(editingPet.id, data);
    } else {
      petStore.add(data);
    }
    setShowPetForm(false);
    setEditingPet(null);
  }

  function handleDeletePet() {
    if (editingPet && window.confirm('Delete pet?')) {
      hapticMedium();
      petStore.remove(editingPet.id);
      setShowPetForm(false);
      setEditingPet(null);
    }
  }

  function handleCancelForm() {
    setShowPetForm(false);
    setEditingPet(null);
  }

  function handleLogout() {
    authStore.logout();
  }

  return (
    <>
      <div
        className={`${styles.overlay} ${open ? styles.overlayActive : ''}`}
        onClick={onClose}
      />
      <div className={`${styles.drawer} ${open ? styles.drawerOpen : ''}`}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.title}>Settings</div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {subPage !== null ? (
          <div className={styles.subPage}>
            <div className={styles.subPageHeader}>
              <button className={styles.backBtn} onClick={() => setSubPage(null)} aria-label="Back">
                <ArrowLeft size={18} />
              </button>
              <span className={styles.subPageTitle}>
                {subPage === 'privacy' && 'Privacy Policy'}
                {subPage === 'disclaimer' && 'Disclaimer'}
                {subPage === 'about' && 'About'}
              </span>
            </div>
            <div className={styles.subPageContent}>
              {subPage === 'privacy' && (
                <>
                  <h4>Data Collection</h4>
                  <p>
                    Cozy Pup collects chat messages and pet profile information you provide
                    in order to deliver personalized pet care suggestions. This data is stored
                    locally on your device using browser local storage.
                  </p>
                  <h4>Third-Party Services</h4>
                  <p>
                    Your messages may be processed by third-party AI services to generate
                    responses. We do not sell or share your personal data with advertisers.
                  </p>
                  <h4>Your Rights</h4>
                  <p>
                    You can delete all your data at any time by logging out. This will remove
                    your pet profiles, chat history, and preferences from local storage.
                  </p>
                </>
              )}
              {subPage === 'disclaimer' && (
                <p>
                  AI suggestions are for reference only and do not constitute veterinary
                  advice. In emergencies, please contact a veterinarian immediately.
                </p>
              )}
              {subPage === 'about' && (
                <div className={styles.aboutContent}>
                  <h2 className={styles.aboutName}>Cozy Pup</h2>
                  <p className={styles.aboutVersion}>Version 1.0.0</p>
                  <p className={styles.aboutTagline}>Your pet's personal butler</p>
                </div>
              )}
            </div>
          </div>
        ) : showPetForm ? (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>
              {editingPet ? 'Edit Pet' : 'Add Pet'}
            </div>
            <PetForm
              pet={editingPet ?? undefined}
              onSave={handleSavePet}
              onCancel={handleCancelForm}
            />
            {editingPet && (
              <button
                className={styles.addPetBtn}
                style={{ color: 'var(--red)', borderColor: 'var(--red)', marginTop: 12 }}
                onClick={handleDeletePet}
              >
                <Trash2 size={16} />
                Delete Pet
              </button>
            )}
          </div>
        ) : (
          <>
            {/* Account */}
            <div className={styles.section}>
              <div className={styles.sectionLabel}>Account</div>
              <div className={styles.accountCard}>
                <div className={styles.accountAvatar}>
                  {auth.user?.name?.charAt(0).toUpperCase() ?? '?'}
                </div>
                <div className={styles.accountInfo}>
                  <h4>{auth.user?.name ?? 'Unknown'}</h4>
                  <p>{auth.user?.email ?? ''}</p>
                </div>
              </div>
            </div>

            {/* My Pets */}
            <div className={styles.section}>
              <div className={styles.sectionLabel}>My Pets</div>
              {pets.map(pet => (
                <div key={pet.id} className={styles.petCard} onClick={() => handleEditPet(pet)}>
                  <div className={`${styles.petAvatar} ${pet.species === 'dog' ? styles.petAvatarDog : styles.petAvatarCat}`}>
                    {pet.species === 'dog' ? <Dog size={22} /> : <Cat size={22} />}
                  </div>
                  <div className={styles.petInfo}>
                    <h4>{pet.name}</h4>
                    <p>{pet.breed}{pet.weight != null ? ` · ${pet.weight}kg` : ''}</p>
                  </div>
                  <div
                    className={styles.petColorDot}
                    style={{ background: pet.color }}
                  />
                  <ChevronRight size={14} className={styles.chevron} />
                </div>
              ))}
              <button className={styles.addPetBtn} onClick={handleAddPet}>
                <Plus size={16} />
                Add Pet
              </button>
            </div>

            {/* Preferences */}
            <div className={styles.section}>
              <div className={styles.sectionLabel}>Preferences</div>
              <div className={styles.settingRow}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconNotif}`}>
                    <Bell size={18} />
                  </div>
                  <div className={styles.settingText}>
                    <h5>Push Notifications</h5>
                    <p>Reminders & health insights</p>
                  </div>
                </div>
                <button
                  className={`${styles.toggle} ${notifications ? styles.toggleOn : ''}`}
                  onClick={handleToggleNotifications}
                  role="switch"
                  aria-checked={notifications}
                  aria-label="Push Notifications"
                >
                  <span className={styles.toggleKnob} />
                </button>
              </div>
              <div className={styles.settingRow}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconMed}`}>
                    <Pill size={18} />
                  </div>
                  <div className={styles.settingText}>
                    <h5>Medication Reminders</h5>
                    <p>Deworming, vaccines</p>
                  </div>
                </div>
                <button
                  className={`${styles.toggle} ${medication ? styles.toggleOn : ''}`}
                  onClick={handleToggleMedication}
                  role="switch"
                  aria-checked={medication}
                  aria-label="Medication Reminders"
                >
                  <span className={styles.toggleKnob} />
                </button>
              </div>
              <div className={styles.settingRow}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconInsight}`}>
                    <BarChart3 size={18} />
                  </div>
                  <div className={styles.settingText}>
                    <h5>Health Insights</h5>
                    <p>Trend alerts & weekly digest</p>
                  </div>
                </div>
                <button
                  className={`${styles.toggle} ${insights ? styles.toggleOn : ''}`}
                  onClick={handleToggleInsights}
                  role="switch"
                  aria-checked={insights}
                  aria-label="Health Insights"
                >
                  <span className={styles.toggleKnob} />
                </button>
              </div>
            </div>

            {/* Legal */}
            <div className={styles.section}>
              <div className={styles.sectionLabel}>Legal</div>
              <div className={styles.settingRow} style={{ cursor: 'pointer' }} onClick={() => setSubPage('privacy')}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconPrivacy}`}>
                    <Shield size={18} />
                  </div>
                  <div className={styles.settingText}><h5>Privacy Policy</h5></div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </div>
              <div className={styles.settingRow} style={{ cursor: 'pointer' }} onClick={() => setSubPage('disclaimer')}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconAbout}`}>
                    <FileText size={18} />
                  </div>
                  <div className={styles.settingText}><h5>Disclaimer</h5></div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </div>
              <div className={styles.settingRow} style={{ cursor: 'pointer' }} onClick={() => setSubPage('about')}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconAbout}`}>
                    <Info size={18} />
                  </div>
                  <div className={styles.settingText}>
                    <h5>About Cozy Pup</h5>
                    <p>Version 1.0.0</p>
                  </div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </div>
            </div>

            {/* Logout */}
            <div className={`${styles.section} ${styles.sectionLast}`}>
              <div className={styles.settingRow} style={{ cursor: 'pointer', borderBottom: 'none' }} onClick={handleLogout}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconLogout}`}>
                    <LogOut size={18} />
                  </div>
                  <div className={styles.settingText}>
                    <h5 style={{ color: 'var(--red)' }}>Log Out</h5>
                  </div>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </>
  );
}
