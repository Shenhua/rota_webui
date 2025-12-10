# Contraintes du Planificateur Rota — État Actuel


Cette outil est fait pour caculer le planning d'une équipe de rotation de jour/soirée/nuit. 

Les agents(travailleurs infermières de bloc) peuvent travailler differents nombres de jours par semaine mais les horaires sont fixés.

Jour = 7h30/17h30 soit 10h
Soir = 9h30/19h30 soit 10h
Nuit = 19h39/7h30 soit 12h

Les agents sont assignés a des Salles de bloc ou elles doivent travailler par paires pour les poste de Jour. 

Le Jour, il y a 3 salles d'interventions programées + 1 salle d'urgence le jour. (4 equipes, 8 personnes)
La nuit, il y'a seulement 1 salle d'urgence (1 equipe, 2 personnes).
Le soir 1 agent seulement est posté seul, afin de faire du travail de préparation.

Le but est de trouver un planning sur un certain nombre de semaine pour atteindre un equilibre et equité entre les agents qui puisse etre ensuite reutilisé pour la periode suivante.

Par exemple le planning calculé sur 12 semaines est dupliqué a partir de la semaine 13. Il est donc necessaire que les contraintes soient respectées egalement sur la periode suivante (eg. pas plus de 48h sur 7 jours glissants entre semaine 12 et 13).

Il est necessaire de pouvoir egalement avoir une option de calcule de planning des weekends. Les weekends sont un planning totalement decorellé du planning de semaine.

## Planning de semaine


### Contraintes Dures (Hard Constraints)
> Ces contraintes DOIVENT être respectées. Une solution qui les viole est invalide.

#### 1. Couverture des postes
- [ ] Chaque poste doit être pourvu pour chaque jour de chaque semaine
- [ ] Les postes D (Jour), N (Nuit) nécessitent 2 personnes (une paire)
- [ ] Le poste S (Soir) nécessite 1 personne seule

#### 2. Limite de travail par jour
- [ ] Une personne ne peut travailler qu'UN SEUL poste par jour

#### 3. Repos après nuit
- [ ] Configurable: "Repos après nuit" dans les paramètres avancés
- [ ] Si activé: une personne ayant travaillé en N ne peut pas travailler le jour suivant

#### 4. EDO (Jour de Repos Gagné)
- [ ] Les personnes éligibles à l'EDO ont 1 jour de repos toutes les 2 semaines
- [ ] Alternance 50/50 entre deux groupes par semaine
- [ ] Possibilité de fixer un jour précis pour l'EDO (Lun, Mar, Mer, Jeu, Ven)
- [ ] Les personnes en EDO ne travaillent pas ce jour-là

#### 5. Maximums
- [ ] Possibilité de fixer un maximum de nuits sur l'horizon (`max_nights`) par personne
- [ ] Nuits consécutives max (configurable dans l'UI mais pas implémenté dans solver)
- [ ] Il est formellement interdit de travailler plus de 48h sur 7 jours glissants. (ne s'applique pas au calendrier du weekend).

---

### Contraintes Souples (Soft Constraints)
> Ces contraintes sont optimisées mais peuvent être violées. Chaque violation a un poids.
Il est important de noter toutes contraintes souples qui sont violé a la fin du calcule ainsi que leur valeur afin que le manager puisse décider de rattrapage au cas par cas. Le resultat final doit montré le calendrier avec les jours qui n'ont pas pu être respecté, ou il manque du personnel afin que le manager puisse combler le manque avec des agents exterieurs.

#### 6. Équité des nuits (σ Nuits)
- [ ] **Poids: 10** (configurable: 0-20)
- [ ] Minimiser l'écart max-min des nuits **PAR COHORTE** (4j vs 3j)
- [ ] Equité proportionnelle au temps de travail (pas implémenté)

#### 7. Équité des soirs (σ Soirs)
- [ ] **Poids: 3** (configurable: 0-20)
- [ ] Minimiser l'écart max-min des soirs **PAR COHORTE**

#### 8. Écart à la cible (Deviation)
- [ ] **Poids: 5** (configurable: 0-20)
- [ ] Minimiser |jours_travaillés - cible| pour chaque personne
- [ ] Cible = (jours_par_semaine × semaines) - jours_EDO

#### 9. Éviter Soir→Jour (Clopening)
- [ ] **Poids: 1** (configurable: 0-10)
- [ ] Pénaliser les enchaînements Soir suivi d'un Jour le lendemain

---


## Planning des Weekends

Durant les weekend il y a seulement 1 salle d'urgence ouverte a la fois (1 equipe, 2 personnes).
Cette salle est ouverte en non-stop 24h donc est couverte par l'equipe de jour et de nuit. Pas de soir.

Une personne peut etre eligible ou non a travailler le weekend.

Les agents peuvent travailler 12h ou 24h. Si une personne travaille 24h elle peut se trouver dans une situation ou son binome changera au bout de 12, eg. ne pas uniquement mettre en place des binomes de 24h et 12h separement.


### Contraintes Dures (Hard Constraints)
> Ces contraintes DOIVENT être respectées. Une solution qui les viole est invalide.

#### 1. Couverture des postes
- [ ] Chaque poste doit être pourvu pour chaque jour de chaque weekend
- [ ] Les postes D (Jour), N (Nuit) nécessitent 2 personnes (une paire)

#### 2. Limite de travail par jour
- [ ] Une personne ne peut travailler qu'UN SEUL poste par jour

#### 3. Limite de travail par weekend
- [ ] Une personne ne peut travailler que 24h maximum par weekend

### Contraintes Souples (Soft Constraints)
> Ces contraintes sont optimisées mais peuvent être violées. Chaque violation a un poids.

#### 1. Équité 
- [ ] Essayer de minimiser le fait de travailler le samedi et le dimanche pour une personne
- [ ] Essayer de minimiser les ecarts sur la periode (horizon) entre le nombre de shifts de 12h et ceux de 24h entre les agents.
- [ ] Essayer de minimiser les ecarts sur la periode (horizon) entre le nombre de samedi et dimanche travaillés entre les agents.

---


## Details et Q&A

### Préférences Individuelles
> Attributs par personne pour personnaliser le planning

#### Implémentées dans le modèle Person mais PAS dans le solver:
- [ ] `prefers_night` — Préfère les nuits
- [ ] `no_evening` — Ne pas affecter aux soirs
- [ ] `team` — Équipe (pour groupement cohorte by-team)

#### Implémentées:
- [ ] `workdays_per_week` — Jours de travail par semaine (3, 4, ou 5)
- [ ] `edo_eligible` — Éligible à l'EDO
- [ ] `edo_fixed_day` — Jour fixe pour l'EDO
- [ ] `max_nights` — Maximum de nuits sur l'horizon

---

### Paramètres de Configuration

| Paramètre | Type | Description |
|-----------|------|-------------|
| `weeks` | int | Nombre de semaines à planifier |
| `tries` | int | Nombre d'essais multi-seed |
| `seed` | int | Graine aléatoire (0 = auto) |
| `time_limit` | int | Limite de temps solver (secondes) |
| `fairness_mode` | enum | Mode cohorte: by-wd, by-team, none |

---

### À Compléter / Clarifier

1. **Proportionnalité des nuits**: Les 3j travaillent actuellement autant de nuits que les 4j. Faut-il proportionner?
- OUI

2. **Nuits consécutives**: Le slider existe mais la contrainte n'est pas dans le solver.
- A IMPLEMENTER

3. **Préférences individuelles**: `prefers_night` et `no_evening` ne sont pas utilisés.
- A IMPLEMENTER

4. **Équipes**: Le mode `by-team` existe mais le champ `team` n'est pas exploité.
- A IMPLEMENTER

5. **Calcul du nombre de postes**: Actuellement dynamique basé sur l'effectif. Faut-il le rendre configurable?
- DETAILS PLUS HAUT DANS LA SPECIFICATION

6. **Week-ends**: Pas de gestion spéciale (les jours sont Lun-Ven uniquement).
- DETAILS PLUS HAUT DANS LA SPECIFICATION

7. **Staffing Numbers (Weekday)**
Jour: 4 salles × 2 personnes = 8 personnes/jour
Nuit: 1 salle × 2 personnes = 2 personnes/nuit
Soir: 1 personne seule
Question: Is this the FIXED staffing for every day (Lun-Ven)? Currently the code derives staffing dynamically based on team size.
- YES THIS IS THE FIXED STAFFING IF WE HAVE GAPS IN THE SCHEDULE (NO STAFFING) the manager will have to fill the gaps with external contractors

8. **Difference between Jour and Soir**
Jour = 7h30-17h30 (10h)
Soir = 9h30-19h30 (10h)
Question: These shifts overlap (9h30-17h30). Is this intentional? Or should Soir be 17h30-19h30 (evening after day shift)?
- IT IS INTENTIONAL THE TYPE OF WORK IS DIFFERENT

9. **48h/7 Rolling Days Constraint**
The spec says: "formellement interdit de travailler plus de 48h sur 7 jours glissants"

Question: With shifts of 10h (Jour/Soir) and 12h (Nuit), how do we count hours? Example:

4 × Jour (10h) + 1 × Nuit (12h) = 52h → violation?
Or is it simpler: max 4 shifts per rolling 7 days?
- THE HOURS NEEDS TO BE ACCOUNTED FOR REAL, NOT THE NUMBER OF SHIFTS OR TYPES

10. **Weekend Planning Structure**
The spec mentions weekends are "totalement décorrélé" from weekday planning.

Question:

Is weekend planning a separate solver run with its own output?
Should the UI have two tabs: "Planning Semaine" and "Planning Weekend"?
For weekends: is it Sat+Sun only, or Sat+Sun across multiple weeks?
- WE CAN HAVE A SEPARATED WEEKEND SOLVER, OPTIONNALY ACTIVATED IN THE UI. IF ACTIVATED A SECOND TAB WILL BE ADDED

11. **Weekend Shift Duration**
"Les agents peuvent travailler 12h ou 24h"

Question:

12h = one shift (D or N)?
24h = both D+N on same day?
Can someone work 24h Saturday + 24h Sunday = 48h total?
- AS STATED IN HARD CONSTRAINTS NO ONE CAN WORK MORE THAN 24H PER WEEKEND. IF SOMEONE WORKS 24h ON SATURDAY IT MEANS IT WILL WORK THE DAY SHIFT + THE NIGHT SHIFT BUT CANNOT WORK THE FOLLOWING DAY.

12. **Circular Constraint (Week 12 → Week 1)**
"les contraintes soient respectées également sur la période suivante"

Question: Should the solver ensure that Week N + Week 1 (when schedule repeats) doesn't violate the 48h rule or night-rest rule?
- NO THE 48H 7 DAYS RULE DOES NOT APPLY ACROSS WEEKS AND WEEKENDS. AN AGENT CAN WORK 48H IN A 7 DAYS PERIOD AND AN ADDITIONAL 24H IF THESE ARE WEEKENDS HOURS.

**DECISION TECHNIQUE:** La contrainte de 48h glissants est implémentée avec une relaxation ("soft constraint") à très forte pénalité. Cela permet au solver de trouver une solution même si la contrainte est mathématiquement impossible sur certaines péridodes, en signalant les violations spécifiques au manager. Les heures de week-end compte pour 0 dans ce calcul (car gérées séparément), mais la fenêtre glisse bien "à travers" les week-ends pour vérifier les enchaînements Vendredi-Lundi.