export type BookingCapabilities = {
  business_category: string;
  is_restaurant: boolean;
  allows_group_services: boolean;
  has_individual_passes: boolean;
};

export const EMPTY_BOOKING_CAPABILITIES: BookingCapabilities = {
  business_category: "", is_restaurant: false, allows_group_services: false, has_individual_passes: false,
};
