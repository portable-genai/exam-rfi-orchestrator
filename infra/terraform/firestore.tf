# firestore.tf : the case store this vertical writes (Native mode, regional, CMEK).
#
# General Principle map:
#   P-03 (residency): the database is regional in var.region, validated against
#         allowed_regions, so exam correspondence, waivers and extension records never leave the
#         deployment's country.
#   P-09 (CMEK explicit): the database encrypts under the regional key from kms.tf, and the
#         Firestore service-agent key binding is declared there. Firestore created WITHOUT a
#         cmek_config succeeds and encrypts under Google-managed keys, and the console shows no
#         difference; the failure mode is a silent downgrade rather than an error, which is why
#         the binding and this block are added in the same commit as the resource.
#   P-05 (retention): delete protection is on. A case store holding the record of what was
#         produced to a supervisor is not something a stack teardown should be able to remove.
#
# This database backs CaseStorePort (exam_rfi_orchestrator.adapters.gcp.case_store). The
# COLLECTION inside it is per-deployment configuration, read three-state through Settings from
# EXAMRFI_CASE_COLLECTION: unset and emptied both arrive as "" and the adapter refuses, because
# a waiver or an extension resolved from the wrong collection is worse than one not resolved at
# all. Terraform owns the database; the collection is created by first write, as Firestore
# collections always are, so there is no collection resource to declare here.

resource "google_firestore_database" "cases" {
  # google-beta: cmek_config is not in the GA provider's 7.x schema (see providers.tf).
  provider = google-beta
  project  = var.project_id
  # NAMED, not "(default)". The adapter is not wired yet, so nothing pins the name in
  # code; when it is, it must pass this database explicitly. A named database also
  # keeps a second service in the same project from sharing this one by accident.
  name        = "exam-rfi-cases"
  location_id = local.region # P-03: the EFFECTIVE region, never var.region, which
  # defaults to null; a required argument reading null fails the plan, and an
  # OPTIONAL one silently lands the resource in a US multi-region.
  type = "FIRESTORE_NATIVE"

  cmek_config {
    kms_key_name = google_kms_crypto_key.cmek.id # P-09, and it does not cascade
  }

  # The record of what was produced to a regulator, and when. Deleting it by accident is the
  # failure this guards against; a deliberate removal still needs the flag flipped first.
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"

  depends_on = [
    google_project_service.required,
    google_kms_crypto_key_iam_member.firestore,
  ]
}
