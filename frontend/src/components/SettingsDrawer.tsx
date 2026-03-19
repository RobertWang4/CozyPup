import { useState } from 'react';
import { X, Bell, Pill, BarChart3, Shield, FileText, Info, LogOut, ChevronRight, Plus, Dog, Cat, Trash2 } from 'lucide-react';
import styles from './SettingsDrawer.module.css';
import { usePets, petStore } from '../stores/petStore';
import { useAuth, authStore } from '../stores/authStore';
import PetForm from './PetForm';
import type { Pet } from '../types/pets';

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsDrawer({ open, onClose }: SettingsDrawerProps) {
  const [notifications, setNotifications] = useState(true);
  const [medication, setMedication] = useState(true);
  const [insights, setInsights] = useState(true);

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

        {showPetForm ? (
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
                  onClick={() => setNotifications(!notifications)}
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
                  onClick={() => setMedication(!medication)}
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
                  onClick={() => setInsights(!insights)}
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
              <div className={styles.settingRow} style={{ cursor: 'pointer' }}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconPrivacy}`}>
                    <Shield size={18} />
                  </div>
                  <div className={styles.settingText}><h5>Privacy Policy</h5></div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </div>
              <div className={styles.settingRow} style={{ cursor: 'pointer' }}>
                <div className={styles.settingLeft}>
                  <div className={`${styles.settingIcon} ${styles.iconAbout}`}>
                    <FileText size={18} />
                  </div>
                  <div className={styles.settingText}><h5>Disclaimer</h5></div>
                </div>
                <ChevronRight size={14} className={styles.chevron} />
              </div>
              <div className={styles.settingRow} style={{ cursor: 'pointer' }}>
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
